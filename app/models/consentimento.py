from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import DB_SCHEMA
from app.models.hemocentro import Base


class Consentimento(Base):
    # Registra o historico de consentimento por finalidade para auditoria LGPD.
    __tablename__ = "consentimentos"
    __table_args__ = {"schema": DB_SCHEMA} if DB_SCHEMA else {}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    finalidade: Mapped[str] = mapped_column(String(80), nullable=False)
    versao_termo: Mapped[str] = mapped_column(String(30), nullable=False)
    base_legal: Mapped[str] = mapped_column(String(120), nullable=False)
    concedido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    concedido_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
