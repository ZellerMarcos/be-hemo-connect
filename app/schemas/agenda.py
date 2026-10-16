from datetime import date, datetime, time, timezone
from typing import Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.schemas.triagem import AgendamentoResponse


class Periodo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inicio: time
    fim: time

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.inicio.tzinfo or self.fim.tzinfo or self.inicio.second or self.fim.second or self.inicio.microsecond or self.fim.microsecond:
            raise ValueError("Informe horas locais com precisao de minutos.")
        if self.inicio >= self.fim:
            raise ValueError("O fim do periodo deve ser posterior ao inicio, no mesmo dia.")
        return self


class PeriodoSemanal(Periodo):
    dia_semana: int = Field(ge=0, le=6)


class ExcecaoAgenda(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: date
    periodos: list[Periodo] = Field(max_length=4)


class AgendaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    fuso_horario: str = Field(min_length=1, max_length=100)
    duracao_minutos: int = Field(ge=5, le=240)
    capacidade: int = Field(ge=1, le=1000)
    antecedencia_minutos: int = Field(ge=0, le=10080)
    horizonte_dias: int = Field(ge=1, le=180)
    cancelamento_minutos: int = Field(ge=0, le=10080)
    remarcacao_minutos: int = Field(ge=0, le=10080)
    publicada: bool
    periodos: list[PeriodoSemanal] = Field(min_length=1, max_length=28)
    excecoes: list[ExcecaoAgenda] = Field(max_length=366)
    versao: int = Field(ge=0)

    @field_validator("fuso_horario")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Fuso horario IANA invalido.") from error
        return value

    @model_validator(mode="after")
    def validate_periods(self) -> Self:
        groups = [[p for p in self.periodos if p.dia_semana == day] for day in range(7)]
        if len({exception.data for exception in self.excecoes}) != len(self.excecoes):
            raise ValueError("Nao repita a data de uma excecao.")
        groups.extend(exception.periodos for exception in self.excecoes)
        for periods in groups:
            ordered = sorted(periods, key=lambda period: period.inicio)
            for index, period in enumerate(ordered):
                minutes = (period.fim.hour - period.inicio.hour) * 60 + period.fim.minute - period.inicio.minute
                if minutes % self.duracao_minutos:
                    raise ValueError("Cada periodo deve conter um numero inteiro de horarios.")
                if index and ordered[index - 1].fim > period.inicio:
                    raise ValueError("Periodos de funcionamento nao podem se sobrepor.")
        return self


class PendenciaLegada(BaseModel):
    id: int
    agendado_em: datetime


class AgendaResponse(BaseModel):
    configurada: bool
    configuracao: AgendaConfig | None
    pendencias_legadas: list[PendenciaLegada]


class HorarioResponse(BaseModel):
    id: int
    inicio: datetime
    fim: datetime
    vagas_disponiveis: int

    @field_serializer("inicio", "fim")
    def utc_timestamp(self, value: datetime) -> str:
        return value.replace(tzinfo=timezone.utc).isoformat()


class DiaDisponibilidade(BaseModel):
    data: date
    motivo: str | None
    horarios: list[HorarioResponse]


class DisponibilidadeResponse(BaseModel):
    hemocentro_id: int
    fuso_horario: str | None
    situacao: Literal["DISPONIVEL", "SEM_AGENDA", "INATIVO", "SEM_VAGAS"]
    mensagem: str
    dias: list[DiaDisponibilidade]
    avisos: list[str]


class AlteracaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    versao: int = Field(ge=1)
    chave_requisicao: UUID


class RemarcacaoRequest(AlteracaoRequest):
    horario_id: int = Field(gt=0)


class AlteracaoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    acao: str
    agendado_anterior: datetime
    agendado_novo: datetime | None
    ocorrido_em: datetime

    @field_serializer("agendado_anterior", "agendado_novo", "ocorrido_em")
    def utc_timestamp(self, value: datetime | None) -> str | None:
        return value.replace(tzinfo=timezone.utc).isoformat() if value else None


class ReservaResponse(AgendamentoResponse):
    fuso_horario: str | None
    pode_cancelar: bool
    pode_remarcar: bool
    motivo_cancelamento: str | None
    motivo_remarcacao: str | None
    alteracoes: list[AlteracaoResponse]
