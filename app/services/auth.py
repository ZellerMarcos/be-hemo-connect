from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.two_factor_code import TwoFactorCode
from app.models.usuario import Usuario
from app.security.two_factor import generate_code, hash_code, verify_code
from app.security.password import verify_password
from app.services.email import send_two_factor_code


CODE_VALIDITY = timedelta(minutes=5)
INACTIVITY_TIMEOUT = timedelta(minutes=45)


def authenticate_user(db: Session, email: str, password: str) -> Usuario | None:
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None or usuario.status != "ATIVO":
        return None
    if not verify_password(password, usuario.senha_hash):
        return None
    return usuario


def update_last_activity(db: Session, email: str) -> Usuario | None:
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None:
        return None
    usuario.last_activity_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return usuario


def validate_active_session(db: Session, email: str) -> Usuario:
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None or usuario.status != "ATIVO":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida.",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if usuario.last_activity_at is None:
        usuario.last_activity_at = now
        db.commit()
        return usuario

    if now - usuario.last_activity_at > INACTIVITY_TIMEOUT:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada por inatividade.",
        )

    usuario.last_activity_at = now
    db.commit()
    return usuario


def logout_user(db: Session, email: str) -> None:
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is not None:
        usuario.last_activity_at = None
        db.commit()


def issue_two_factor_code(db: Session, usuario: Usuario) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Somente o código mais recente deve permanecer válido para este login.
    pending_codes = db.scalars(
        select(TwoFactorCode).where(
            TwoFactorCode.usuario_id == usuario.id,
            TwoFactorCode.used_at.is_(None),
        )
    ).all()
    for pending_code in pending_codes:
        pending_code.used_at = now

    code = generate_code()
    two_factor_code = TwoFactorCode(
        usuario_id=usuario.id,
        code_hash=hash_code(code),
        expires_at=now + CODE_VALIDITY,
        created_at=now,
    )
    db.add(two_factor_code)
    db.commit()
    try:
        send_two_factor_code(str(usuario.email), code)
    except Exception:
        # Evita deixar no banco um desafio que nunca chegou ao usuário.
        db.delete(two_factor_code)
        db.commit()
        raise


def verify_two_factor_code(db: Session, email: str, code: str) -> bool:
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None or usuario.status != "ATIVO":
        return False

    two_factor_code = db.scalar(
        select(TwoFactorCode)
        .where(
            TwoFactorCode.usuario_id == usuario.id,
            TwoFactorCode.used_at.is_(None),
        )
        .order_by(TwoFactorCode.created_at.desc())
    )
    if two_factor_code is None:
        return False

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # A validade é conferida antes da comparação e o código só é consumido
    # depois de uma correspondência bem-sucedida.
    if two_factor_code.expires_at <= now or not verify_code(code, two_factor_code.code_hash):
        return False

    # Marcar o registro como usado impede a reutilização do mesmo código.
    two_factor_code.used_at = now
    db.commit()
    return True