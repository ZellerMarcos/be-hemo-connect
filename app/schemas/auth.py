from pydantic import BaseModel, ConfigDict, EmailStr

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