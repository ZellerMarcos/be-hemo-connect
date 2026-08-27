from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


Perfil = Literal[
    "DOADOR",
    "ENFERMEIRO",
    "MEDICO",
    "RECEPCIONISTA",
    "RESPONSAVEL_HEMOCENTRO",
    "ADMINISTRADOR",
]
Status = Literal["ATIVO", "INATIVO"]


class UsuarioCreate(BaseModel):
    nome: str = Field(min_length=1)
    cpf: str = Field(pattern=r"^\d{11}$")
    email: EmailStr
    senha_hash: str = Field(min_length=1)
    perfil: Perfil
    status: Status
    hemocentro_id: int | None = None


class UsuarioUpdate(BaseModel):
    nome: str = Field(min_length=1)
    cpf: str = Field(pattern=r"^\d{11}$")
    email: EmailStr
    perfil: Perfil
    status: Status
    hemocentro_id: int | None = None


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    cpf: str
    email: EmailStr
    perfil: Perfil
    status: Status
    hemocentro_id: int | None