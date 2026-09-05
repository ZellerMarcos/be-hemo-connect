import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.password_reset_token import PasswordResetToken
from app.models.two_factor_code import TwoFactorCode
from app.models.usuario import Usuario
from app.security.password import hash_password, verify_password
from app.security.two_factor import generate_code, hash_code, verify_code
from app.services.email import send_password_reset_link, send_two_factor_code


logger = logging.getLogger(__name__)
CODE_VALIDITY = timedelta(minutes=5)
RESET_TOKEN_VALIDITY = timedelta(minutes=15)
# A sessão do usuário considera o tempo sem atividade: 45 minutos sem requisição válida encerra a sessão.
INACTIVITY_TIMEOUT = timedelta(minutes=45)
# A proteção contra brute force considera até 5 erros em 15 minutos antes de bloquear a conta por 1 hora.
FAILED_LOGIN_ATTEMPTS_LIMIT = 5
FAILED_LOGIN_WINDOW = timedelta(minutes=15)
LOCKOUT_DURATION = timedelta(hours=1)


def get_login_error_detail(db: Session, email: str) -> str:
    # Monta a mensagem mais útil possível para o cliente antes do bloqueio definitivo da conta.
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None or usuario.status != "ATIVO":
        return "E-mail ou senha inválidos."

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if usuario.locked_until is not None and usuario.locked_until > now:
        return "Conta temporariamente bloqueada. Tente novamente em 1 hora."

    if usuario.failed_login_window_started_at is not None:
        window_elapsed = now - usuario.failed_login_window_started_at
        if window_elapsed <= FAILED_LOGIN_WINDOW:
            remaining_attempts = max(FAILED_LOGIN_ATTEMPTS_LIMIT - usuario.failed_login_attempts, 1)
            return (
                "E-mail ou senha inválidos. Restam "
                f"{remaining_attempts} tentativas antes do bloqueio por 1 hora."
            )

    return "E-mail ou senha inválidos."


def authenticate_user(db: Session, email: str, password: str) -> Usuario | None:
    # Primeiro passo do login: localiza o usuário pelo e-mail e valida status e senha.
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None or usuario.status != "ATIVO":
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Se o usuário ainda está bloqueado, a API deve responder explicitamente com 403 para não revelar demais.
    if usuario.locked_until is not None and usuario.locked_until > now:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta temporariamente bloqueada. Tente novamente em 1 hora.",
        )

    # Quando o prazo de bloqueio expirou, o sistema limpa o estado de bloqueio para permitir um novo ciclo.
    if usuario.locked_until is not None and usuario.locked_until <= now:
        usuario.locked_until = None
        usuario.failed_login_attempts = 0
        usuario.failed_login_window_started_at = None

    if not verify_password(password, usuario.senha_hash):
        # Qualquer senha incorreta é contabilizada em uma janela de 15 minutos.
        if (
            usuario.failed_login_window_started_at is None
            or now - usuario.failed_login_window_started_at > FAILED_LOGIN_WINDOW
        ):
            usuario.failed_login_window_started_at = now
            usuario.failed_login_attempts = 1
        else:
            usuario.failed_login_attempts += 1

        # Ao atingir o limite, a conta fica bloqueada por 1 hora para reduzir ataques de força bruta.
        if usuario.failed_login_attempts >= FAILED_LOGIN_ATTEMPTS_LIMIT:
            usuario.locked_until = now + LOCKOUT_DURATION

        db.commit()
        return None

    # Tentativa bem-sucedida reinicia o contador para evitar que o bloqueio persista indevidamente.
    usuario.failed_login_attempts = 0
    usuario.failed_login_window_started_at = None
    usuario.locked_until = None
    db.commit()
    return usuario


def update_last_activity(db: Session, email: str) -> Usuario | None:
    # Atualiza a última atividade do usuário no banco para medir o tempo de inatividade.
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None:
        return None
    usuario.last_activity_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return usuario


def validate_active_session(db: Session, email: str) -> Usuario:
    # Valida se a sessão continua ativa e se o usuário não excedeu o limite de 45 minutos sem atividade.
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None or usuario.status != "ATIVO":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida.",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if usuario.last_activity_at is None:
        # Primeira validação: marca a atividade atual para iniciar a contagem do timeout.
        usuario.last_activity_at = now
        db.commit()
        return usuario

    if now - usuario.last_activity_at > INACTIVITY_TIMEOUT:
        # Quando o tempo de inatividade supera o limite, a API nega o acesso como se fosse logout.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada por inatividade.",
        )

    # Qualquer requisição válida renova a atividade para manter a sessão viva.
    usuario.last_activity_at = now
    db.commit()
    return usuario


def logout_user(db: Session, email: str) -> None:
    # Logout do backend: limpa a última atividade do usuário para encerrar a sessão imediatamente.
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is not None:
        usuario.last_activity_at = None
        db.commit()


def issue_two_factor_code(db: Session, usuario: Usuario) -> None:
    # Gera um código de 2FA para confirmar que a pessoa é realmente o dono da conta.
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
        # Envia o código ao e-mail do usuário, caso a entrega falhe, o registro é descartado.
        send_two_factor_code(str(usuario.email), code)
    except Exception:
        # Evita deixar no banco um desafio que nunca chegou ao usuário.
        db.delete(two_factor_code)
        db.commit()
        raise


def verify_two_factor_code(db: Session, email: str, code: str) -> bool:
    # Confere se o código enviado pelo usuário é o código válido e ainda não expirou.
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
    # A validade é conferida antes da comparação, e o código só é consumido após a confirmação.
    if two_factor_code.expires_at <= now or not verify_code(code, two_factor_code.code_hash):
        return False

    # Marcar o registro como usado impede a reutilização do mesmo código.
    two_factor_code.used_at = now
    db.commit()
    return True


def generate_password_reset_token() -> str:
    # O token bruto é gerado com alto nível de aleatoriedade para reduzir predição.
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_reset_token(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_reset_token(token), token_hash)


def request_password_reset(db: Session, email: str) -> bool:
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None or usuario.status != "ATIVO":
        logger.info("Solicitacao de recuperacao de senha rejeitada para email=%s", email)
        return False

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    pending_tokens = db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.usuario_id == usuario.id,
            PasswordResetToken.used_at.is_(None),
        )
    ).all()
    for token in pending_tokens:
        token.used_at = now

    token = generate_password_reset_token()
    reset_token = PasswordResetToken(
        usuario_id=usuario.id,
        token_hash=hash_reset_token(token),
        expires_at=now + RESET_TOKEN_VALIDITY,
        created_at=now,
    )
    db.add(reset_token)
    db.commit()
    reset_url = f"http://localhost:5173/redefinir-senha?token={token}"
    try:
        send_password_reset_link(str(usuario.email), reset_url)
    except Exception:
        db.delete(reset_token)
        db.commit()
        raise
    logger.info("Solicitacao de recuperacao de senha registrada para email=%s", email)
    return True


def reset_password(db: Session, token: str, new_password: str) -> bool:
    token_hash = hash_reset_token(token)
    db_token = db.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.token_hash == token_hash,
        )
    )
    if db_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de redefinição inválido ou expirado.",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if db_token.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de redefinição inválido ou expirado.",
        )

    usuario = db.get(Usuario, db_token.usuario_id)
    if usuario is None or usuario.status != "ATIVO":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de redefinição inválido ou expirado.",
        )

    usuario.senha_hash = hash_password(new_password)
    db_token.used_at = now
    db.commit()
    return True