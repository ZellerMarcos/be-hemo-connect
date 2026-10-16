from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


Perfil = Literal[
    "DOADOR",
    "ENFERMEIRO",
    "MEDICO",
    "RECEPCIONISTA",
    "RESPONSAVEL_HEMOCENTRO",
    "ADMINISTRADOR",
]
Status = Literal["ATIVO", "INATIVO"]
TipoSanguineo = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
CorenUF = Literal[
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]


class UsuarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=1)
    cpf: str = Field(pattern=r"^\d{11}$")
    email: EmailStr
    senha: str = Field(min_length=1)
    perfil: Perfil
    status: Status
    hemocentro_id: int | None = None
    data_nascimento: date | None = None
    telefone: str | None = Field(default=None, min_length=1, max_length=30)
    tipo_sanguineo: TipoSanguineo | None = None
    coren_numero: str | None = Field(default=None, pattern=r"^[0-9]{1,20}$")
    coren_uf: CorenUF | None = None
    # Confirma o aceite explicito no fluxo de cadastro.
    consentimento_aceito: bool
    # Versiona o texto do termo para auditoria futura.
    consentimento_versao: str = Field(min_length=1, max_length=30)
    # Define as finalidades aceitas para persistencia de consentimento.
    consentimento_finalidades: list[str] = Field(min_length=1)

    @field_validator("coren_numero", "coren_uf", mode="before")
    @classmethod
    def normalize_coren(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_credential(self) -> Self:
        if self.perfil == "ENFERMEIRO" and (not self.coren_numero or not self.coren_uf):
            raise ValueError("Informe o número do COREN e a UF para o perfil ENFERMEIRO.")
        if self.perfil != "ENFERMEIRO" and (self.coren_numero is not None or self.coren_uf is not None):
            raise ValueError("COREN é exclusivo do cadastro de enfermeiro.")
        return self


class EnfermeiroSolicitacao(UsuarioCreate):
    perfil: Literal["ENFERMEIRO"] = "ENFERMEIRO"
    status: Literal["INATIVO"] = "INATIVO"
    hemocentro_id: None = None


class UsuarioUpdate(BaseModel):
    nome: str = Field(min_length=1)
    cpf: str = Field(pattern=r"^\d{11}$")
    email: EmailStr
    perfil: Perfil
    status: Status
    hemocentro_id: int | None = None
    data_nascimento: date | None = None
    telefone: str | None = Field(default=None, min_length=1, max_length=30)
    tipo_sanguineo: TipoSanguineo | None = None


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    cpf: str
    email: EmailStr
    perfil: Perfil
    status: Status
    hemocentro_id: int | None
    data_nascimento: date | None
    telefone: str | None
    tipo_sanguineo: TipoSanguineo | None
    coren_numero: str | None
    coren_uf: CorenUF | None
    aprovacao_pendente: bool


class EnfermeiroPendenteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    email: EmailStr
    coren_numero: str
    coren_uf: CorenUF


class AprovacoesPendentesResponse(BaseModel):
    itens: list[EnfermeiroPendenteResponse]
    total: int
    pagina: int
    tamanho: int


class AprovarEnfermeiroRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hemocentro_id: int = Field(gt=0)
    conferencia_confirmada: Literal[True]

    @field_validator("conferencia_confirmada", mode="before")
    @classmethod
    def require_confirmation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("A conferência profissional deve ser confirmada explicitamente.")
        return value