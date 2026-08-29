from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LoginTwoFactorRequired,
    TwoFactorVerifyRequest,
    TwoFactorVerifyResponse,
)
from app.services.auth import (
    authenticate_user,
    issue_two_factor_code,
    logout_user,
    update_last_activity,
    validate_active_session,
    verify_two_factor_code,
)


router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=LoginResponse | LoginTwoFactorRequired)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    # Fluxo de login: primeiro valida credenciais e, se corretas, dispara o segundo fator.
    usuario = authenticate_user(db, data.email, data.senha)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
        )
    # A senha correta inicia o segundo fator, mas ainda não conclui o login.
    issue_two_factor_code(db, usuario)
    return LoginTwoFactorRequired()


@router.post("/2fa/verify", response_model=TwoFactorVerifyResponse)
def verify_two_factor(data: TwoFactorVerifyRequest, db: Session = Depends(get_db)):
    # Verifica o código de 2FA; caso esteja válido, a sessão passa a contar atividade para o timeout.
    if not verify_two_factor_code(db, str(data.email), data.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código de verificação inválido.",
        )
    # Em autenticação bem-sucedida, registra a atividade atual para renovar a sessão do backend.
    update_last_activity(db, str(data.email))
    return TwoFactorVerifyResponse(authenticated=True)


@router.post("/logout")
def logout(
    email: Annotated[str | None, Header(alias="x-user-email", convert_underscores=True)] = None,
    db: Session = Depends(get_db),
):
    # Logout manual: o servidor remove a marcação de atividade para encerrar a sessão por segurança.
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida.",
        )
    logout_user(db, email)
    return {"logged_out": True}


def require_active_session(
    email: Annotated[str | None, Header(alias="x-user-email", convert_underscores=True)] = None,
    db: Session = Depends(get_db),
):
    # Dependência compartilhada para todas as rotas protegidas: valida a sessão e o timeout de inatividade.
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida.",
        )
    return validate_active_session(db, email)
