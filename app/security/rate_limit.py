import hashlib
import ipaddress
import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import case, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.rate_limit_counter import RateLimitCounter


logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def request_origin(request: Request) -> str | None:
    # O servidor ASGI normaliza proxies confiaveis; a aplicacao nao rele headers.
    direct_origin = request.client.host if request.client else None
    verified_peer = request.scope.get("state", {}).get("verified_proxy_peer")
    if os.getenv("APP_ENV", "development").lower() == "production" and (
        not verified_peer or direct_origin == verified_peer
    ):
        return None
    try:
        if direct_origin is not None:
            return str(ipaddress.ip_address(direct_origin))
    except ValueError:
        pass
    logger.warning("Origem ASGI sem IP valido; controle por origem indisponivel.")
    return None


def _scope_key(action: str, scope: str, identifier: str) -> str:
    normalized = json.dumps(
        ["hemo-connect:rate-limit:v2", action, scope, identifier.strip().lower()],
        ensure_ascii=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def enforce_rate_limit(
    db: Session,
    *,
    action: str,
    scope: str,
    identifier: str,
    limit: int,
    window: timedelta,
) -> None:
    if limit < 1:
        raise RuntimeError("O limite de requisicoes deve ser maior que zero.")

    now = _utcnow()
    cutoff = now - window
    dialect = db.get_bind().dialect.name
    insert_factory = {
        "postgresql": postgresql_insert,
        "sqlite": sqlite_insert,
    }.get(dialect)
    if insert_factory is None:
        raise RuntimeError(f"Rate limiting nao suporta o dialeto {dialect}.")

    statement = insert_factory(RateLimitCounter).values(
        action=action,
        scope_key=_scope_key(action, scope, identifier),
        window_started_at=now,
        attempts=1,
    )
    reset_window = RateLimitCounter.window_started_at <= cutoff
    statement = statement.on_conflict_do_update(
        index_elements=[RateLimitCounter.action, RateLimitCounter.scope_key],
        set_={
            "attempts": case(
                (reset_window, 1),
                else_=RateLimitCounter.attempts + 1,
            ),
            "window_started_at": case(
                (reset_window, now),
                else_=RateLimitCounter.window_started_at,
            ),
        },
    ).returning(
        RateLimitCounter.attempts,
        RateLimitCounter.window_started_at,
    )
    try:
        if scope == "global":
            db.execute(delete(RateLimitCounter).where(
                RateLimitCounter.window_started_at < now - timedelta(hours=24),
            ))
        attempts, window_started_at = db.execute(statement).one()
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        logger.error("Persistencia do limitador indisponivel | action=%s", action)
        raise HTTPException(
            status_code=503,
            detail="Proteção de acesso temporariamente indisponível. Tente novamente mais tarde.",
        ) from error
    if attempts <= limit:
        return

    retry_after = max(
        1,
        math.ceil((window_started_at + window - now).total_seconds()),
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Muitas tentativas. Aguarde antes de tentar novamente.",
        headers={"Retry-After": str(retry_after)},
    )


def enforce_public_endpoint_limits(
    db: Session,
    request: Request,
    *,
    action: str,
    account_identifier: str,
    account_limit: int,
    origin_limit: int,
    global_limit: int,
    window: timedelta,
) -> None:
    enforce_rate_limit(
        db, action=action, scope="global", identifier="all",
        limit=global_limit, window=window,
    )
    origin = request_origin(request)
    if origin is not None:
        enforce_rate_limit(
            db, action=action, scope="origin", identifier=origin,
            limit=origin_limit, window=window,
        )
    enforce_rate_limit(
        db, action=action, scope="account", identifier=account_identifier,
        limit=account_limit, window=window,
    )
