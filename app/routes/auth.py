from typing import Annotated
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LoginTwoFactorRequired,
    EmailChangeConfirmRequest,
    EmailChangeConfirmResponse,
    EmailChangeRequest,
    EmailChangeRequestResponse,
    PasswordResetRequest,
    PasswordResetResponse,
    PasswordResetTokenRequest,
    PasswordResetTokenResponse,
    TwoFactorVerifyRequest,
    TwoFactorVerifyResponse,
)
from app.security.session import authenticate_session, revoke_session
from app.security.rate_limit import enforce_public_endpoint_limits
from app.services.auth import (
    authenticate_user,
    confirm_email_change,
    get_login_error_detail,
    issue_two_factor_code,
    logout_user,
    request_password_reset,
    request_email_change,
    reset_password,
    verify_two_factor_code,
)


router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=LoginTwoFactorRequired)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    enforce_public_endpoint_limits(
        db, request, action="login", account_identifier=str(data.email),
        account_limit=10, origin_limit=30, global_limit=1000,
        window=timedelta(minutes=15),
    )
    # Fluxo de login: primeiro valida credenciais e, se corretas, dispara o segundo fator.
    usuario = authenticate_user(db, data.email, data.senha)
    if usuario is None:
        # O backend informa ao cliente quantas tentativas ainda restam antes do bloqueio de 1 hora.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=get_login_error_detail(db, str(data.email)),
        )
    enforce_public_endpoint_limits(
        db, request, action="2fa_send", account_identifier=str(data.email),
        account_limit=3, origin_limit=15, global_limit=1000,
        window=timedelta(minutes=15),
    )
    # A senha correta inicia o segundo fator, mas ainda não conclui o login.
    return issue_two_factor_code(db, usuario)


@router.post("/2fa/verify", response_model=TwoFactorVerifyResponse)
def verify_two_factor(
    data: TwoFactorVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    enforce_public_endpoint_limits(
        db, request, action="2fa_verify", account_identifier=data.challenge_id,
        account_limit=10, origin_limit=30, global_limit=2000,
        window=timedelta(minutes=15),
    )
    # Verifica o código de 2FA; caso esteja válido, a sessão passa a contar atividade para o timeout.
    authenticated = verify_two_factor_code(
        db, data.challenge_id, data.challenge_secret, data.code,
    )
    if authenticated is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código de verificação inválido.",
        )
    usuario, token = authenticated
    return TwoFactorVerifyResponse(
        authenticated=True,
        nome=usuario.nome,
        usuario=LoginResponse.model_validate(usuario),
        access_token=token,
    )


@router.post("/forgot-password", response_model=PasswordResetResponse)
def forgot_password(
    data: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    enforce_public_endpoint_limits(
        db, request, action="password_reset_request",
        account_identifier=str(data.email),
        account_limit=3, origin_limit=15, global_limit=1000,
        window=timedelta(minutes=15),
    )
    # A resposta uniforme evita revelar se o e-mail informado pertence a uma conta ativa.
    request_password_reset(db, str(data.email))
    # O cliente recebe o mesmo resultado tanto para usuário existente quanto inexistente.
    return PasswordResetResponse(sent=True)


@router.post("/reset-password", response_model=PasswordResetTokenResponse)
def reset_password_route(data: PasswordResetTokenRequest, db: Session = Depends(get_db)):
    # O serviço valida e consome o token antes de alterar a senha; a rota apenas traduz o resultado.
    reset_password(db, data.token, data.senha)
    # A resposta confirma a operação sem devolver token, hash ou senha.
    return PasswordResetTokenResponse(reset=True)


@router.post("/logout")
def logout(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
):
    # Logout manual: o servidor remove a marcação de atividade para encerrar a sessão por segurança.
    usuario = authenticate_session(db, authorization)
    if authorization is None:
        raise HTTPException(401, "Sessão inválida.")
    revoke_session(db, authorization)
    logout_user(db, usuario.email)
    # O estado persistido foi limpo; a resposta apenas confirma o encerramento da sessão.
    return {"logged_out": True}


def require_active_session(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
):
    # Dependência compartilhada para todas as rotas protegidas: valida a sessão e o timeout de inatividade.
    return authenticate_session(db, authorization)


@router.get("/me", response_model=LoginResponse)
def current_user(usuario: Usuario = Depends(require_active_session)):
    return usuario


@router.post("/email-change/request", response_model=EmailChangeRequestResponse)
def request_email_change_route(
    data: EmailChangeRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_active_session),
):
    pending_email = request_email_change(
        db, usuario, str(data.new_email), data.current_password,
    )
    return EmailChangeRequestResponse(pending_email=pending_email)


@router.post("/email-change/confirm", response_model=EmailChangeConfirmResponse)
def confirm_email_change_route(
    data: EmailChangeConfirmRequest,
    db: Session = Depends(get_db),
):
    return EmailChangeConfirmResponse(email=confirm_email_change(db, data.token))
