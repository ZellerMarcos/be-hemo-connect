from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import DB_SCHEMA
from app.models.hemocentro import Base


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = {"schema": DB_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    cpf: Mapped[str] = mapped_column(String(11), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    perfil: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    hemocentro_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Guarda o instante da última atividade válida do usuário para controlar a expiração por inatividade.
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=None,
    )
    # Mantém a quantidade de tentativas inválidas consecutivas em uma janela de 15 minutos.
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Informa quando começou a janela de tentativas falhas para resetar o contador em 15 minutos.
    failed_login_window_started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=None,
    )
    # Bloqueia o login por 1 hora após a quinta tentativa inválida dentro da janela aceitável.
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=None,
    )