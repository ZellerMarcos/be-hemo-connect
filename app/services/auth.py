import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.password_reset_token import PasswordResetToken
from app.models.email_change_token import EmailChangeToken
from app.models.two_factor_code import TwoFactorCode
from app.models.usuario import Usuario
from app.security.audit import registrar_evento
from app.security.password import hash_password, verify_password
from app.security.two_factor import (
    VERIFIER_FORMAT,
    generate_challenge_nonce,
    generate_challenge_secret,
    generate_code,
    hash_challenge_secret,
    hash_code,
    verify_code,
)
from app.security.session import issue_session, revoke_user_authentication
from app.schemas.auth import LoginTwoFactorRequired
from app.services.email import (
    send_email_change_confirmation,
    send_email_change_notice,
    send_password_reset_email,
    send_two_factor_code,
)


logger = logging.getLogger(__name__)
CODE_VALIDITY = timedelta(minutes=5)
RESET_TOKEN_VALIDITY = timedelta(minutes=15)
EMAIL_CHANGE_TOKEN_VALIDITY = timedelta(minutes=15)
# A proteção contra brute force considera até 5 erros em 15 minutos antes de bloquear a conta por 1 hora.
FAILED_LOGIN_ATTEMPTS_LIMIT = 5
FAILED_LOGIN_WINDOW = timedelta(minutes=15)
LOCKOUT_DURATION = timedelta(hours=1)
TWO_FACTOR_FAILED_ATTEMPTS_LIMIT = 5


def get_login_error_detail(db: Session, email: str) -> str:
    # Monta a mensagem mais útil possível para o cliente antes do bloqueio definitivo da conta.
    # A mensagem varia conforme o estado interno, mas nunca revela se a senha armazenada existe.
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None or usuario.status != "ATIVO" or usuario.aprovacao_pendente:
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
    if usuario is None or usuario.status != "ATIVO" or usuario.aprovacao_pendente:
        registrar_evento(db, "login", "falha", ator=email, motivo="credenciais_invalidas")
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Se o usuário ainda está bloqueado, a API deve responder explicitamente com 403 para não revelar demais.
    if usuario.locked_until is not None and usuario.locked_until > now:
        registrar_evento(db, "login", "bloqueado", ator=email, motivo="limite_tentativas")
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
        registrar_evento(
            db,
            "login",
            "bloqueado" if usuario.locked_until is not None else "falha",
            ator=email,
            motivo="credenciais_invalidas",
        )
        return None

    # Tentativa bem-sucedida reinicia o contador para evitar que o bloqueio persista indevidamente.
    usuario.failed_login_attempts = 0
    usuario.failed_login_window_started_at = None
    usuario.locked_until = None
    db.commit()
    registrar_evento(db, "login", "sucesso", ator=email, user_id=usuario.id)
    return usuario


def logout_user(db: Session, email: str) -> None:
    # Logout do backend: limpa a última atividade do usuário para encerrar a sessão imediatamente.
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is not None:
        usuario.last_activity_at = None
        db.commit()
        # O logout e registrado somente depois de limpar a atividade persistida.
        registrar_evento(db, "logout", "sucesso", ator=email, user_id=usuario.id)


def issue_two_factor_code(db: Session, usuario: Usuario) -> LoginTwoFactorRequired:
    # Gera um código de 2FA para confirmar que a pessoa é realmente o dono da conta.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    usuario = db.scalars(select(Usuario).where(
        Usuario.id == usuario.id,
    ).with_for_update().execution_options(populate_existing=True)).one()
    if usuario.status != "ATIVO" or usuario.aprovacao_pendente:
        raise HTTPException(401, "Sessão inválida.")
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
    challenge_nonce = generate_challenge_nonce()
    challenge_secret = generate_challenge_secret()
    two_factor_code = TwoFactorCode(
        usuario_id=usuario.id,
        code_hash=hash_code(
            code,
            usuario_id=usuario.id,
            challenge_nonce=challenge_nonce,
            challenge_secret=challenge_secret,
        ),
        challenge_nonce=challenge_nonce,
        key_version=VERIFIER_FORMAT,
        verifier_format=VERIFIER_FORMAT,
        challenge_token_hash=hash_challenge_secret(challenge_secret),
        failed_attempts=0,
        expires_at=now + CODE_VALIDITY,
        created_at=now,
    )
    db.add(two_factor_code)
    db.commit()
    # O desafio fica persistido antes do envio para que a validacao encontre somente o codigo atual.
    try:
        # Envia o código ao e-mail do usuário, caso a entrega falhe, o registro é descartado.
        send_two_factor_code(str(usuario.email), code)
    except Exception:
        # Evita deixar no banco um desafio que nunca chegou ao usuário.
        db.delete(two_factor_code)
        db.commit()
        # A falha de entrega tambem deixa uma evidencia de auditoria, sem registrar o codigo.
        registrar_evento(db, "2fa_envio", "falha", ator=str(usuario.email), user_id=usuario.id)
        raise
    # O log confirma a tentativa de entrega sem expor o valor do código.
    logger.info("Token 2FA enviado | status=sucesso | email=%s", usuario.email)
    registrar_evento(db, "2fa_envio", "sucesso", ator=str(usuario.email), user_id=usuario.id)
    return LoginTwoFactorRequired(
        challenge_id=challenge_nonce, challenge_secret=challenge_secret,
    )


def verify_two_factor_code(
    db: Session, challenge_id: str, challenge_secret: str, code: str,
) -> tuple[Usuario, str] | None:
    challenge = db.scalar(select(TwoFactorCode).where(
        TwoFactorCode.challenge_nonce == challenge_id,
        TwoFactorCode.verifier_format == VERIFIER_FORMAT,
    ))
    if (
        challenge is None or challenge.challenge_token_hash is None
        or not hmac.compare_digest(
            hash_challenge_secret(challenge_secret), challenge.challenge_token_hash,
        )
    ):
        registrar_evento(db, "2fa_validacao", "falha", motivo="desafio_invalido")
        return None

    usuario = db.scalar(select(Usuario).where(
        Usuario.id == challenge.usuario_id,
    ).with_for_update().execution_options(populate_existing=True))
    db.refresh(challenge)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if (
        usuario is None or usuario.status != "ATIVO" or usuario.aprovacao_pendente
        or challenge.used_at is not None or challenge.expires_at <= now
        or challenge.failed_attempts >= TWO_FACTOR_FAILED_ATTEMPTS_LIMIT
    ):
        registrar_evento(db, "2fa_validacao", "falha", motivo="desafio_indisponivel")
        return None

    if not verify_code(
        code, challenge.code_hash, usuario_id=usuario.id,
        challenge_nonce=challenge.challenge_nonce, challenge_secret=challenge_secret,
    ):
        next_attempt = TwoFactorCode.failed_attempts + 1
        db.execute(update(TwoFactorCode).where(
            TwoFactorCode.id == challenge.id,
            TwoFactorCode.used_at.is_(None),
        ).values(
            failed_attempts=next_attempt,
            used_at=case(
                (next_attempt >= TWO_FACTOR_FAILED_ATTEMPTS_LIMIT, now),
                else_=TwoFactorCode.used_at,
            ),
        ))
        registrar_evento(
            db, "2fa_validacao", "falha", ator=usuario.email,
            user_id=usuario.id, motivo="codigo_invalido_ou_expirado",
        )
        return None

    try:
        consumed = db.execute(update(TwoFactorCode).where(
            TwoFactorCode.id == challenge.id,
            TwoFactorCode.used_at.is_(None),
            TwoFactorCode.expires_at > now,
            TwoFactorCode.failed_attempts < TWO_FACTOR_FAILED_ATTEMPTS_LIMIT,
        ).values(used_at=now).returning(TwoFactorCode.id)).scalar_one_or_none()
        if consumed is None:
            db.rollback()
            registrar_evento(db, "2fa_validacao", "falha", motivo="codigo_consumido")
            return None
        registrar_evento(
            db, "2fa_validacao", "sucesso", ator=usuario.email,
            user_id=usuario.id, commit=False,
        )
        token = issue_session(db, usuario, commit=False)
        db.commit()
    except (SQLAlchemyError, HTTPException):
        db.rollback()
        logger.error("Falha na transacao de autenticacao 2FA; sessao nao confirmada.")
        raise
    logger.info("Autenticacao 2FA e sessao confirmadas | user_id=%s", usuario.id)
    return usuario, token


def generate_password_reset_token() -> str:
    # O token bruto é gerado com alto nível de aleatoriedade para reduzir predição.
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_reset_token(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_reset_token(token), token_hash)


def request_password_reset(db: Session, email: str) -> bool:
    # O pedido registra sucesso/falha no fluxo de auditoria, mas nunca persiste o token bruto.
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None or usuario.status != "ATIVO" or usuario.aprovacao_pendente:
        # O aviso registra a tentativa operacional, enquanto a resposta externa permanece uniforme.
        logger.warning(
            "Usuário solicitou uma redefinição de senha | status=falha | email=%s",
            email,
        )
        registrar_evento(db, "reset_senha_solicitacao", "falha", ator=email, motivo="usuario_invalido")
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
    # Registra a criação da solicitação antes de iniciar o envio do link por e-mail.
    logger.info(
        "Usuário solicitou uma redefinição de senha | status=solicitada | email=%s",
        email,
    )
    # Usa a origem do frontend configurada no ambiente e mantém localhost para desenvolvimento.
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    reset_url = f"{frontend_url}/reset-password?token={token}"
    try:
        send_password_reset_email(str(usuario.email), reset_url)
    except Exception:
        # Registra a falha operacional sem expor o token ou detalhes sensíveis do provedor de e-mail.
        logger.warning(
            "Token de redefinição não enviado | status=falha | email=%s",
            email,
        )
        db.delete(reset_token)
        db.commit()
        # Sem entrega, o token deixa de ser utilizavel e a falha fica registrada sem o link.
        raise
    # Confirma que o link foi entregue ao serviço de envio sem registrar o token em si.
    logger.info("Token enviado | status=sucesso | email=%s", email)
    registrar_evento(db, "reset_senha_solicitacao", "sucesso", ator=email, user_id=usuario.id)
    return True


def reset_password(db: Session, token: str, new_password: str) -> bool:
    # A busca compara somente o hash do token recebido; o valor bruto nunca vai para logs ou banco.
    token_hash = hash_reset_token(token)
    db_token = db.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.token_hash == token_hash,
        )
    )
    if db_token is None:
        # Tokens ausentes, utilizados ou pertencentes a outro valor são registrados sem revelar o conteúdo recebido.
        # O mesmo motivo cobre token inexistente e já consumido para evitar enumeracao.
        logger.warning(
            "Reset de senha ou pedido mal sucedido | status=falha | motivo=token inválido ou expirado"
        )
        registrar_evento(db, "reset_senha", "falha", motivo="token_invalido_ou_expirado")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de redefinição inválido ou expirado.",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if db_token.expires_at <= now:
        # Expiracao e tratada como falha de validacao, sem devolver detalhes do registro ao cliente.
        logger.warning(
            "Reset de senha ou pedido mal sucedido | status=falha | motivo=token inválido ou expirado"
        )
        registrar_evento(db, "reset_senha", "falha", motivo="token_invalido_ou_expirado")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de redefinição inválido ou expirado.",
        )

    usuario = db.get(Usuario, db_token.usuario_id)
    if usuario is None or usuario.status != "ATIVO" or usuario.aprovacao_pendente:
        # Um token ligado a conta inativa não pode alterar credenciais.
        logger.warning(
            "Reset de senha ou pedido mal sucedido | status=falha | motivo=usuário inválido ou inativo"
        )
        registrar_evento(db, "reset_senha", "falha", motivo="usuario_invalido")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de redefinição inválido ou expirado.",
        )

    # Consome o token de forma atômica para que duas requisições simultâneas não usem o mesmo link.
    token_update = db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.id == db_token.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
    )
    if token_update.rowcount != 1:
        db.rollback()
        # A atualização condicional protege contra duas requisições concorrentes consumirem o mesmo token.
        logger.warning(
            "Reset de senha ou pedido mal sucedido | status=falha | motivo=token já utilizado ou expirado | email=%s",
            usuario.email,
        )
        registrar_evento(db, "reset_senha", "falha", ator=str(usuario.email), user_id=usuario.id, motivo="token_indisponivel")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de redefinição inválido ou expirado.",
        )

    # A senha só é alterada depois que esta requisição assume o uso exclusivo do token.
    usuario.senha_hash = hash_password(new_password)
    revoke_user_authentication(db, usuario.id)
    usuario.last_activity_at = None
    db.commit()
    # O evento de sucesso permite auditar a operação sem registrar a nova senha ou o token.
    logger.info("Reset bem sucedido | status=sucesso | email=%s", usuario.email)
    registrar_evento(db, "reset_senha", "sucesso", ator=str(usuario.email), user_id=usuario.id)
    return True


def request_email_change(
    db: Session,
    usuario: Usuario,
    new_email: str,
    current_password: str,
) -> str:
    normalized_email = new_email.strip().lower()
    if not verify_password(current_password, usuario.senha_hash):
        registrar_evento(
            db, "troca_email_solicitacao", "falha",
            ator=str(usuario.email), user_id=usuario.id, motivo="reautenticacao_invalida",
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Senha atual inválida.")
    if normalized_email == str(usuario.email).lower():
        raise HTTPException(status.HTTP_409_CONFLICT, "O novo e-mail deve ser diferente do atual.")
    existing_user = db.scalar(
        select(Usuario.id).where(func.lower(Usuario.email) == normalized_email)
    )
    if existing_user is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este e-mail já está em uso.")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(update(EmailChangeToken).where(
        EmailChangeToken.usuario_id == usuario.id,
        EmailChangeToken.used_at.is_(None),
    ).values(used_at=now))
    raw_token = generate_password_reset_token()
    change_token = EmailChangeToken(
        usuario_id=usuario.id,
        new_email=normalized_email,
        token_hash=hash_reset_token(raw_token),
        expires_at=now + EMAIL_CHANGE_TOKEN_VALIDITY,
        created_at=now,
    )
    db.add(change_token)
    db.commit()

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    confirmation_url = f"{frontend_url}/confirm-email?token={raw_token}"
    try:
        send_email_change_confirmation(normalized_email, confirmation_url)
        send_email_change_notice(str(usuario.email), normalized_email)
    except Exception:
        change_token.used_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        registrar_evento(
            db, "troca_email_solicitacao", "falha",
            ator=str(usuario.email), user_id=usuario.id, motivo="falha_notificacao",
        )
        raise

    registrar_evento(
        db, "troca_email_solicitacao", "sucesso",
        ator=str(usuario.email), user_id=usuario.id,
    )
    return normalized_email


def confirm_email_change(db: Session, raw_token: str) -> str:
    token_hash = hash_reset_token(raw_token)
    change_token = db.scalar(select(EmailChangeToken).where(
        EmailChangeToken.token_hash == token_hash,
        EmailChangeToken.used_at.is_(None),
    ))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if change_token is None or change_token.expires_at <= now:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Token de troca de e-mail inválido ou expirado.",
        )
    usuario = db.get(Usuario, change_token.usuario_id)
    if usuario is None or usuario.status != "ATIVO" or usuario.aprovacao_pendente:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Token de troca de e-mail inválido ou expirado.",
        )
    if db.scalar(select(Usuario.id).where(
        func.lower(Usuario.email) == change_token.new_email.lower(),
        Usuario.id != usuario.id,
    )) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este e-mail já está em uso.")

    consumed = db.execute(update(EmailChangeToken).where(
        EmailChangeToken.id == change_token.id,
        EmailChangeToken.used_at.is_(None),
        EmailChangeToken.expires_at > now,
    ).values(used_at=now))
    if consumed.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Token de troca de e-mail inválido ou expirado.",
        )

    old_email = str(usuario.email)
    usuario.email = change_token.new_email
    revoke_user_authentication(db, usuario.id)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Este e-mail já está em uso.") from error
    registrar_evento(
        db, "troca_email_confirmacao", "sucesso",
        ator=old_email, user_id=usuario.id,
    )
    return str(usuario.email)