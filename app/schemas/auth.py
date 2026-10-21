from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.usuario import Perfil, Status


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str


class LoginResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: EmailStr
    perfil: Perfil
    status: Status
    hemocentro_id: int | None


class LoginTwoFactorRequired(BaseModel):
    requires_2fa: bool = True
    challenge_id: str
    challenge_secret: str = Field(repr=False)
    expires_in: int = 300


class TwoFactorVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    challenge_secret: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$", repr=False)
    code: str = Field(pattern=r"^\d{6}$")


class TwoFactorVerifyResponse(BaseModel):
    authenticated: bool
    nome: str
    usuario: LoginResponse
    access_token: str
    token_type: str = "bearer"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetResponse(BaseModel):
    sent: bool = True


class PasswordResetTokenRequest(BaseModel):
    token: str
    senha: str = Field(min_length=8)


class PasswordResetTokenResponse(BaseModel):
    reset: bool = True


class EmailChangeRequest(BaseModel):
    new_email: EmailStr
    current_password: str = Field(min_length=1)


class EmailChangeRequestResponse(BaseModel):
    pending_email: EmailStr


class EmailChangeConfirmRequest(BaseModel):
    token: str = Field(min_length=1)


class EmailChangeConfirmResponse(BaseModel):
    changed: bool = True
    email: EmailStr