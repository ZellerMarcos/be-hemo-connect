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
    # O endpoint retorna apenas o resultado da validação; não cria sessão ou token.
    if not verify_two_factor_code(db, str(data.email), data.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código de verificação inválido.",
        )
    update_last_activity(db, str(data.email))
    return TwoFactorVerifyResponse(authenticated=True)


@router.post("/logout")
def logout(
    email: Annotated[str | None, Header(alias="x-user-email", convert_underscores=True)] = None,
    db: Session = Depends(get_db),
):
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
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida.",
        )
    return validate_active_session(db, email)
