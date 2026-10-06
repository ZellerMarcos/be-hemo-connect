from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


TriagemStatus = Literal["AGUARDANDO_TRIAGEM", "EM_TRIAGEM", "APTO", "INAPTO", "ENCAMINHADO_MEDICO"]
ResultadoTriagem = Literal["APTO", "INAPTO", "ENCAMINHADO_MEDICO"]


class RespostaPreTriagem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    pergunta: str = Field(min_length=1, max_length=500)
    resposta: str = Field(min_length=1, max_length=2000)


class AgendamentoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hemocentro_id: int = Field(gt=0)
    agendado_em: datetime
    respostas_pre_triagem: list[RespostaPreTriagem] = Field(default_factory=list, max_length=100)

    @field_validator("agendado_em")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Informe data/hora com fuso horário.")
        return value.astimezone(timezone.utc).replace(tzinfo=None)


class AgendamentoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    hemocentro_id: int
    agendado_em: datetime
    status: str
    recebido_em: datetime | None


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
