from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.hemocentro import Base


class AgendaHemocentro(Base):
    __tablename__ = "agendas_hemocentros"

    hemocentro_id: Mapped[int] = mapped_column(ForeignKey("hemocentros.id"), primary_key=True)
    fuso_horario: Mapped[str] = mapped_column(String(100))
    duracao_minutos: Mapped[int] = mapped_column(Integer)
    capacidade: Mapped[int] = mapped_column(Integer)
    antecedencia_minutos: Mapped[int] = mapped_column(Integer)
    horizonte_dias: Mapped[int] = mapped_column(Integer)
    cancelamento_minutos: Mapped[int] = mapped_column(Integer)
    remarcacao_minutos: Mapped[int] = mapped_column(Integer)
    periodos: Mapped[list[dict]] = mapped_column(JSON)
    excecoes: Mapped[list[dict]] = mapped_column(JSON)
    publicada: Mapped[bool] = mapped_column(Boolean)
    versao: Mapped[int] = mapped_column(Integer, default=1)


class HorarioAgenda(Base):
    __tablename__ = "horarios_agenda"
    __table_args__ = (UniqueConstraint("hemocentro_id", "inicio", name="uq_horario_unidade_inicio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hemocentro_id: Mapped[int] = mapped_column(ForeignKey("hemocentros.id"), index=True)
    inicio: Mapped[datetime] = mapped_column(DateTime, index=True)
    fim: Mapped[datetime] = mapped_column(DateTime)
    capacidade: Mapped[int] = mapped_column(Integer)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class AlteracaoAgendamento(Base):
    __tablename__ = "alteracoes_agendamento"
    __table_args__ = (UniqueConstraint("agendamento_id", "chave_requisicao", name="uq_alteracao_requisicao"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agendamento_id: Mapped[int] = mapped_column(ForeignKey("agendamentos.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    acao: Mapped[str] = mapped_column(String(30))
    chave_requisicao: Mapped[str | None] = mapped_column(String(36), nullable=True)
    versao_origem: Mapped[int] = mapped_column(Integer)
    horario_anterior_id: Mapped[int | None] = mapped_column(ForeignKey("horarios_agenda.id"), nullable=True)
    horario_novo_id: Mapped[int | None] = mapped_column(ForeignKey("horarios_agenda.id"), nullable=True)
    agendado_anterior: Mapped[datetime] = mapped_column(DateTime)
    agendado_novo: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ocorrido_em: Mapped[datetime] = mapped_column(DateTime)
