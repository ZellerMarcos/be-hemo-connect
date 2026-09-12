from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.usuario import Perfil, Status


class ConsentimentoResponse(BaseModel):
    # Representa o estado de um consentimento por finalidade para leitura do titular.
    model_config = ConfigDict(from_attributes=True)

    finalidade: str
    versao_termo: str
    base_legal: str
    concedido: bool
    concedido_em: datetime
    revogado_em: datetime | None


class RevogarConsentimentoRequest(BaseModel):
    # Payload minimo para indicar qual finalidade deve ser revogada.
    finalidade: str = Field(min_length=1, max_length=80)


class RevogarConsentimentoResponse(BaseModel):
    # Confirma a revogacao efetiva com timestamp para rastreabilidade.
    revogado: bool
    finalidade: str
    revogado_em: datetime


class TitularDadosResponse(BaseModel):
    # Reune os dados pessoais e os consentimentos vinculados ao proprio titular.
    id: int
    nome: str
    cpf: str
    email: EmailStr
    perfil: Perfil
    status: Status
    hemocentro_id: int | None
    consentimentos: list[ConsentimentoResponse]


class ExportacaoTitularResponse(BaseModel):
    # Encapsula a exportacao de dados com momento de emissao.
    titular: TitularDadosResponse
    exportado_em: datetime


class ExclusaoTitularResponse(BaseModel):
    # Retorno padrao para operacoes de exclusao/anonimizacao do titular.
    excluido: bool
    mensagem: str
