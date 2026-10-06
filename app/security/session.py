import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.auth_session import AuthSession
from app.models.usuario import Usuario
from app.security.audit import registrar_evento


INACTIVITY_TIMEOUT = timedelta(minutes=45)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def issue_session(db: Session, usuario: Usuario) -> str:
    if usuario.status != "ATIVO" or usuario.aprovacao_pendente:
        raise HTTPException(401, "Sessão inválida.")
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(AuthSession(
        usuario_id=usuario.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        created_at=now,
        last_activity_at=now,
    ))
    usuario.last_activity_at = now
    registrar_evento(db, "sessao", "sucesso", ator=usuario.email, user_id=usuario.id, motivo="sessao_criada")
    return token


def authenticate_session(db: Session, authorization: str | None) -> Usuario:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sessão inválida.")
    token = authorization.removeprefix("Bearer ").strip()
    session = db.scalar(select(AuthSession).where(
        AuthSession.token_hash == hashlib.sha256(token.encode()).hexdigest(),
        AuthSession.revoked_at.is_(None),
    ))
    now = utcnow()
    usuario = db.get(Usuario, session.usuario_id) if session else None
    if session is None or usuario is None or usuario.status != "ATIVO" or usuario.aprovacao_pendente:
        raise HTTPException(401, "Sessão inválida.")
    if now - session.last_activity_at > INACTIVITY_TIMEOUT:
        session.revoked_at = now
        registrar_evento(db, "sessao", "falha", user_id=usuario.id, motivo="inatividade")
        raise HTTPException(401, "Sessão expirada por inatividade.")
    # A condição evita renovar uma sessão que foi revogada por outra requisição.
    renewed = db.execute(update(AuthSession).where(
        AuthSession.id == session.id,
        AuthSession.revoked_at.is_(None),
    ).values(last_activity_at=now))
    if renewed.rowcount != 1:
        db.rollback()
        raise HTTPException(401, "Sessão inválida.")
    usuario.last_activity_at = now
    db.commit()
    return usuario


def revoke_session(db: Session, authorization: str) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    db.execute(update(AuthSession).where(
        AuthSession.token_hash == hashlib.sha256(token.encode()).hexdigest(),
        AuthSession.revoked_at.is_(None),
    ).values(revoked_at=utcnow()))
    db.commit()


def revoke_user_sessions(db: Session, usuario_id: int) -> None:
    db.execute(update(AuthSession).where(
        AuthSession.usuario_id == usuario_id,
        AuthSession.revoked_at.is_(None),
    ).values(revoked_at=utcnow()))
