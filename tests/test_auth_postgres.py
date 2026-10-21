import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import AuthSession, TwoFactorCode, Usuario
from app.models.hemocentro import Base
from app.security.audit import verificar_integridade
from app.security.password import hash_password
from app.security.rate_limit import enforce_rate_limit
from app.security.session import issue_session
from app.services.auth import issue_two_factor_code, verify_two_factor_code


SQL_DIRECTORY = Path(__file__).resolve().parents[1] / "sql"


def apply_migration(engine, schema, filename):
    script = (SQL_DIRECTORY / filename).read_text(encoding="utf-8")
    script = script.replace("public.", f'"{schema}".')
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute(script)
        raw.commit()
    finally:
        raw.close()


@pytest.fixture
def postgres_auth():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("PostgreSQL isolado indisponivel; use o TEST_POSTGRES_URL ja suportado.")
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    admin_engine = create_engine(url)
    schema = f"auth_test_{uuid4().hex}"
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        tables = [
            table for table in Base.metadata.sorted_tables
            if table.name not in {"two_factor_codes", "rate_limit_counters"}
        ]
        Base.metadata.create_all(engine, tables=tables)
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE two_factor_codes (
                    id SERIAL PRIMARY KEY,
                    usuario_id INTEGER NOT NULL,
                    code_hash VARCHAR(64) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT now()
                )
            """))
            connection.execute(text("""
                INSERT INTO two_factor_codes (usuario_id, code_hash, expires_at)
                VALUES (1, repeat('a', 64), now() + interval '5 minutes')
            """))
        apply_migration(engine, schema, "005_e3_antiabuso_2fa.sql")
        with engine.begin() as connection:
            connection.execute(text("UPDATE two_factor_codes SET used_at = NULL"))
        apply_migration(engine, schema, "006_e3_desafio_sem_novas_variaveis.sql")
        with Session(engine) as db:
            user = Usuario(
                nome="Titular sintetico", cpf="12345678901", email="test@example.com",
                perfil="DOADOR", status="ATIVO", senha_hash=hash_password("TestPassword123!"),
            )
            db.add(user)
            db.commit()
            user_id = user.id
        yield engine, schema, user_id
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def new_challenge(engine, user_id):
    with Session(engine) as db, patch(
        "app.services.auth.send_two_factor_code",
    ), patch("app.services.auth.generate_code", return_value="123456"):
        return issue_two_factor_code(db, db.get(Usuario, user_id))


def simultaneously(action):
    barrier = Barrier(2)

    def run():
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run) for _ in range(2)]
        return [future.result(timeout=30) for future in futures]


def test_006_upgrade_and_reexecution_preserve_new_challenges(postgres_auth):
    engine, schema, user_id = postgres_auth
    challenge = new_challenge(engine, user_id)
    apply_migration(engine, schema, "006_e3_desafio_sem_novas_variaveis.sql")
    with Session(engine) as db:
        assert db.get(TwoFactorCode, 1).used_at is not None
        current = db.scalar(select(TwoFactorCode).where(
            TwoFactorCode.challenge_nonce == challenge.challenge_id,
        ))
        assert current.used_at is None
        assert current.challenge_token_hash is not None
        with pytest.raises(IntegrityError):
            current.challenge_token_hash = None
            db.commit()
        db.rollback()
        assert verify_two_factor_code(
            db, challenge.challenge_id, challenge.challenge_secret, "123456",
        ) is not None


def test_concurrent_confirmations_issue_exactly_one_session(postgres_auth):
    engine, _, user_id = postgres_auth
    challenge = new_challenge(engine, user_id)

    def verify():
        with Session(engine) as db:
            result = verify_two_factor_code(
                db, challenge.challenge_id, challenge.challenge_secret, "123456",
            )
            return result is not None

    assert sorted(simultaneously(verify)) == [False, True]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 1
        assert verificar_integridade(db) == (True, None)


def test_concurrent_counters_do_not_exceed_threshold(postgres_auth, real_rate_limits):
    engine, _, _ = postgres_auth

    def increment():
        with Session(engine) as db:
            try:
                enforce_rate_limit(
                    db, action="concurrent", scope="account", identifier="test@example.com",
                    limit=1, window=timedelta(minutes=15),
                )
                return 200
            except HTTPException as error:
                return error.status_code

    assert sorted(simultaneously(increment)) == [200, 429]


def test_transaction_failure_does_not_consume_challenge_or_persist_session(postgres_auth):
    engine, _, user_id = postgres_auth
    challenge = new_challenge(engine, user_id)

    def fail_after_session(db, usuario, *, commit):
        issue_session(db, usuario, commit=commit)
        raise SQLAlchemyError("synthetic transaction failure")

    with Session(engine) as db, patch(
        "app.services.auth.issue_session", side_effect=fail_after_session,
    ):
        with pytest.raises(SQLAlchemyError):
            verify_two_factor_code(
                db, challenge.challenge_id, challenge.challenge_secret, "123456",
            )
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
        assert db.scalar(select(TwoFactorCode).where(
            TwoFactorCode.challenge_nonce == challenge.challenge_id,
        )).used_at is None
        assert verificar_integridade(db) == (True, None)
        assert verify_two_factor_code(
            db, challenge.challenge_id, challenge.challenge_secret, "123456",
        ) is not None


def test_concurrent_wrong_codes_reach_five_without_lost_attempts(postgres_auth):
    engine, _, user_id = postgres_auth
    challenge = new_challenge(engine, user_id)
    with Session(engine) as db:
        stored = db.scalar(select(TwoFactorCode).where(
            TwoFactorCode.challenge_nonce == challenge.challenge_id,
        ))
        stored.failed_attempts = 3
        db.commit()

    def wrong_code():
        with Session(engine) as db:
            return verify_two_factor_code(
                db, challenge.challenge_id, challenge.challenge_secret, "000000",
            )

    assert simultaneously(wrong_code) == [None, None]
    with Session(engine) as db:
        stored = db.scalar(select(TwoFactorCode).where(
            TwoFactorCode.challenge_nonce == challenge.challenge_id,
        ))
        assert stored.failed_attempts == 5
        assert stored.used_at is not None
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
