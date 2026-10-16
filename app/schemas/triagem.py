from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


TriagemStatus = Literal["AGUARDANDO_TRIAGEM", "EM_TRIAGEM", "APTO", "INAPTO", "ENCAMINHADO_MEDICO"]
ResultadoTriagem = Literal["APTO", "INAPTO", "ENCAMINHADO_MEDICO"]


class RespostaPreTriagem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    pergunta: str = Field(min_length=1, max_length=500)
    resposta: str = Field(min_length=1, max_length=2000)


class AgendamentoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    horario_id: int = Field(gt=0)
    chave_requisicao: UUID
    respostas_pre_triagem: list[RespostaPreTriagem] = Field(default_factory=list, max_length=100)


class ConfirmarChegada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    versao: int = Field(ge=1)


class AgendamentoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    hemocentro_id: int
    agendado_em: datetime
    status: str
    recebido_em: datetime | None
    horario_id: int | None
    versao: int
    cancelavel_ate: datetime | None
    remarcavel_ate: datetime | None
    cancelado_em: datetime | None

    @field_serializer("agendado_em", "recebido_em", "cancelavel_ate", "remarcavel_ate", "cancelado_em")
    def utc_timestamp(self, value: datetime | None) -> str | None:
        return value.replace(tzinfo=timezone.utc).isoformat() if value else None


class FilaItem(AgendamentoResponse):
    nome: str
    cpf_mascarado: str
    tipo_sanguineo: str | None
    enfermeiro_id: int | None


class FilaResponse(BaseModel):
    itens: list[FilaItem]
    total: int
    pagina: int
    tamanho: int


class IndicadoresResponse(BaseModel):
    pendentes: int
    em_atendimento: int
    concluidas: int
    encaminhadas_medico: int


class DadosDoador(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    nome: str
    cpf: str
    data_nascimento: date | None
    telefone: str | None
    email: str
    tipo_sanguineo: str | None


class AvaliacaoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    enfermeiro_id: int
    iniciada_em: datetime
    finalizada_em: datetime | None
    observacoes: str | None
    resultado: ResultadoTriagem | None
    versao: int


class HistoricoItem(BaseModel):
    agendamento_id: int
    data: datetime
    tipo: Literal["Triagem"] = "Triagem"
    resultado: ResultadoTriagem


class TriagemDetalhe(BaseModel):
    agendamento: AgendamentoResponse
    doador: DadosDoador
    pre_triagem: list[RespostaPreTriagem]
    historico: list[HistoricoItem]
    avaliacao: AvaliacaoResponse | None


class AvaliacaoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    observacoes: str = Field(min_length=1, max_length=10000)
    versao: int = Field(gt=0)


class TriagemFinalizar(AvaliacaoUpdate):
    resultado: ResultadoTriagem
