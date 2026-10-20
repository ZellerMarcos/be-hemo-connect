from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import DB_SCHEMA
from app.models.hemocentro import Base


class TwoFactorCode(Base):
    __tablename__ = "two_factor_codes"
    __table_args__ = {"schema": DB_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    challenge_nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    key_version: Mapped[str] = mapped_column(String(30), nullable=False)
    challenge_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verifier_format: Mapped[str] = mapped_column(
        String(30), nullable=False, default="legacy-hmac-v1",
        server_default="legacy-hmac-v1",
    )
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )