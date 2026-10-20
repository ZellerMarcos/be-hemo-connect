from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import DB_SCHEMA
from app.models.hemocentro import Base


class EmailChangeToken(Base):
    __tablename__ = "email_change_tokens"
    __table_args__ = {"schema": DB_SCHEMA} if DB_SCHEMA else {}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey(f"{DB_SCHEMA + '.' if DB_SCHEMA else ''}usuarios.id"),
        nullable=False,
        index=True,
    )
    new_email: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
