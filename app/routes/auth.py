from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LoginTwoFactorRequired,
    PasswordResetRequest,
    PasswordResetResponse,
    PasswordResetTokenRequest,
    PasswordResetTokenResponse,
    TwoFactorVerifyRequest,
    TwoFactorVerifyResponse,
)
from app.security.session import authenticate_session, issue_session, revoke_session
from app.services.auth import (
    authenticate_user,
    get_login_error_detail,
    issue_two_factor_code,
    logout_user,
    request_password_reset,
    reset_password,
    verify_two_factor_code,
)


router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=LoginResponse | LoginTwoFactorRequired)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    # Fluxo de login: primeiro valida credenciais e, se corretas, dispara o segundo fator.
    usuario = authenticate_user(db, data.email, data.senha)
    if usuario is None:
        # O backend informa ao cliente quantas tentativas ainda restam antes do bloqueio de 1 hora.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=get_login_error_detail(db, str(data.email)),
        )
    # A senha correta inicia o segundo fator, mas ainda não conclui o login.
    issue_two_factor_code(db, usuario)
    # A primeira resposta informa ao frontend que a próxima etapa é a confirmação do código.
    return LoginTwoFactorRequired()


@router.post("/2fa/verify", response_model=TwoFactorVerifyResponse)
def verify_two_factor(data: TwoFactorVerifyRequest, db: Session = Depends(get_db)):
    # Verifica o código de 2FA; caso esteja válido, a sessão passa a contar atividade para o timeout.
    usuario = db.scalar(select(Usuario).where(Usuario.email == str(data.email)))
    if not verify_two_factor_code(db, str(data.email), data.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código de verificação inválido.",
        )
    # Em autenticação bem-sucedida, registra a atividade atual para renovar a sessão do backend.
    if usuario is None:
        raise HTTPException(401, "Sessão inválida.")
    token = issue_session(db, usuario)
    return TwoFactorVerifyResponse(
        authenticated=True,
        nome=usuario.nome,
        usuario=LoginResponse.model_validate(usuario),
        access_token=token,
    )


@router.post("/forgot-password", response_model=PasswordResetResponse)
def forgot_password(data: PasswordResetRequest, db: Session = Depends(get_db)):
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
