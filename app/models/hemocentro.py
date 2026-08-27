from sqlalchemy import Enum, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.database import DB_SCHEMA


class Base(DeclarativeBase):
    pass


class Hemocentro(Base):
    __tablename__ = "hemocentros"
    __table_args__ = {"schema": DB_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    endereco: Mapped[str] = mapped_column(String(500), nullable=False)
    telefone: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("ATIVO", "INATIVO", name="hemocentro_status"), nullable=False
    )