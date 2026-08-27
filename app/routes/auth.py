from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LoginTwoFactorRequired,
    TwoFactorVerifyRequest,
    TwoFactorVerifyResponse,
)
from app.services.auth import authenticate_user, issue_two_factor_code, verify_two_factor_code


router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=LoginResponse | LoginTwoFactorRequired)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    usuario = authenticate_user(db, data.email, data.senha)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
        )
    issue_two_factor_code(db, usuario)
    return LoginTwoFactorRequired()


@router.post("/2fa/verify", response_model=TwoFactorVerifyResponse)
def verify_two_factor(data: TwoFactorVerifyRequest, db: Session = Depends(get_db)):
    if not verify_two_factor_code(db, str(data.email), data.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código de verificação inválido.",
        )
    return TwoFactorVerifyResponse(authenticated=True)