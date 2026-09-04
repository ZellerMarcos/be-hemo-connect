import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


load_dotenv()

raw_database_url = os.getenv("DATABASE_URL", "sqlite:///./hemo_connect.db")
if os.getenv("APP_ENV") == "test":
    DATABASE_URL = "sqlite://"
else:
    DATABASE_URL = raw_database_url

DB_SCHEMA = "dbo" if DATABASE_URL.startswith("mssql") else None

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()