from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.hemocentro import Base


class Agendamento(Base):
    __tablename__ = "agendamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    doador_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    hemocentro_id: Mapped[int] = mapped_column(ForeignKey("hemocentros.id"), index=True)
    agendado_em: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(30), default="AGENDADO", index=True)
    respostas_pre_triagem: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    recebido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recebido_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime)


class Triagem(Base):
    __tablename__ = "triagens"

    id: Mapped[int] = mapped_column(primary_key=True)
    agendamento_id: Mapped[int] = mapped_column(ForeignKey("agendamentos.id"), unique=True)
    enfermeiro_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    iniciada_em: Mapped[datetime] = mapped_column(DateTime)
    finalizada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resultado: Mapped[str | None] = mapped_column(String(30), nullable=True)
    versao: Mapped[int] = mapped_column(default=1)
