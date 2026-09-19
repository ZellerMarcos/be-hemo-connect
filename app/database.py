import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

if os.getenv("APP_ENV") == "test":
    # Testes usam SQLite isolado para não depender de uma instância PostgreSQL externa.
    DATABASE_URL = "sqlite://"
else:
    # Em desenvolvimento e produção, a URL vem do ambiente para manter credenciais fora do código.
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL deve ser definida no arquivo .env")

DB_SCHEMA = None

# SQLite precisa desta opção para permitir o uso da sessão pelo TestClient em múltiplas threads.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    # Cada requisição recebe uma sessão própria, que é sempre fechada após o retorno da rota.
    db = SessionLocal()
    try:
        yield db
    finally:
        # O fechamento libera a conexão mesmo quando a rota termina com exceção.
        db.close()