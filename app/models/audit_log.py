from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import DB_SCHEMA
from app.models.hemocentro import Base


class AuditLog(Base):
    # A tabela guarda a evidencia persistente dos fluxos de autenticacao e seguranca.
    __tablename__ = "audit_logs"
    __table_args__ = {"schema": DB_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # O usuario pode ser desconhecido em falhas anteriores a uma autenticacao concluida.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{DB_SCHEMA + '.' if DB_SCHEMA else ''}usuarios.id"),
        nullable=True,
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # Cada hash aponta para o evento anterior; o primeiro registro inicia a cadeia com nulo.
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # O hash atual protege os campos relevantes contra alteracoes silenciosas.
    current_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
