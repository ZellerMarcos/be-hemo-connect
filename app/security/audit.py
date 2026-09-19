import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


logger = logging.getLogger("app.audit")


def _hash_event(payload: dict[str, Any]) -> str:
    # A serializacao canonica garante que o mesmo evento sempre produza o mesmo hash.
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def registrar_evento(
    db: Session,
    acao: str,
    status: str,
    *,
    ator: str | None = None,
    user_id: int | None = None,
    motivo: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Persiste um evento sem armazenar credenciais, tokens ou códigos temporários."""
    # O fluxo cria um payload seguro, encadeia-o ao evento anterior e persiste o registro
    # antes de emitir a mensagem operacional. Senhas, tokens e codigos nunca entram aqui.
    metadata = {"motivo": motivo} if motivo else {}
    occurred_at = datetime.now(timezone.utc).replace(tzinfo=None)
    # Limita o user-agent para evitar que uma entrada externa cresca sem controle.
    safe_user_agent = user_agent[:500] if user_agent else None
    # O ultimo registro fornece o elo anterior da cadeia de integridade.
    previous = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()))
    previous_hash = previous.current_hash if previous else None
    payload = {
        "actor_email": ator,
        "event_type": acao,
        "ip_address": ip_address,
        "metadata_json": metadata,
        "occurred_at": occurred_at.isoformat(timespec="microseconds"),
        "previous_hash": previous_hash,
        "status": status,
        "user_agent": safe_user_agent,
        "user_id": user_id,
    }
    registro = AuditLog(
        user_id=user_id,
        actor_email=ator,
        event_type=acao,
        status=status,
        ip_address=ip_address,
        user_agent=safe_user_agent,
        metadata_json=metadata,
        occurred_at=occurred_at,
        previous_hash=previous_hash,
        current_hash=_hash_event(payload),
    )
    # O commit torna a evidencia duravel; refresh recupera o ID e os valores gerados pelo banco.
    db.add(registro)
    db.commit()
    db.refresh(registro)

    campos = [f"acao={acao}", f"status={status}"]
    if ator:
        campos.append(f"ator={ator}")
    if motivo:
        campos.append(f"motivo={motivo}")
    mensagem = "AUDIT | " + " | ".join(campos)
    # Falhas e bloqueios ficam em WARNING para destaque operacional; demais eventos ficam em INFO.
    if status in {"falha", "bloqueado"}:
        logger.warning(mensagem)
    else:
        logger.info(mensagem)
    return registro


def verificar_integridade(db: Session) -> tuple[bool, int | None]:
    """Recalcula a cadeia e retorna o primeiro registro inconsistente."""
    # A verificacao percorre a ordem original e compara tanto o elo anterior quanto o hash do evento.
    previous_hash: str | None = None
    registros = db.scalars(select(AuditLog).order_by(AuditLog.id)).all()
    for registro in registros:
        payload = {
            "actor_email": registro.actor_email,
            "event_type": registro.event_type,
            "ip_address": registro.ip_address,
            "metadata_json": registro.metadata_json,
            "occurred_at": registro.occurred_at.isoformat(timespec="microseconds"),
            "previous_hash": previous_hash,
            "status": registro.status,
            "user_agent": registro.user_agent,
            "user_id": registro.user_id,
        }
        if registro.previous_hash != previous_hash or registro.current_hash != _hash_event(payload):
            # O ID retornado permite localizar o primeiro ponto de adulteracao ou inconsistência.
            return False, registro.id
        previous_hash = registro.current_hash
    return True, None
