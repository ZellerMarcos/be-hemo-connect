from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models.hemocentro import Base
from app.models.two_factor_code import TwoFactorCode
from app.models.usuario import Usuario
from app.security.two_factor import hash_code
from app.services.auth import CODE_VALIDITY


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def clean_database():
    with Session(engine) as session:
        session.execute(Base.metadata.tables["two_factor_codes"].delete())
        session.execute(Base.metadata.tables["usuarios"].delete())
        session.commit()


def override_get_db():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def user_payload(status: str = "ATIVO") -> dict[str, object]:
    return {
        "nome": "Joao Silva",
        "cpf": "12345678901",
        "email": "joao@example.com",
        "senha": "SenhaSegura123!",
        "perfil": "DOADOR",
        "status": status,
        "hemocentro_id": None,
    }


def create_user(status: str = "ATIVO") -> None:
    response = client.post("/usuarios", json=user_payload(status))
    assert response.status_code == 201


def test_login_generates_six_digit_code_and_sends_email():
    create_user()
    sent_codes: list[str] = []

    recipients: list[str] = []

    def capture_email(recipient: str, code: str) -> None:
        recipients.append(recipient)
        sent_codes.append(code)

    with patch("app.services.auth.send_two_factor_code", side_effect=capture_email):
        response = client.post(
            "/auth/login",
            json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
        )

    assert response.status_code == 200
    assert response.json() == {"requires_2fa": True}
    assert len(sent_codes) == 1
    assert recipients == ["joao@example.com"]
    assert sent_codes[0].isdigit() and len(sent_codes[0]) == 6

    with Session(engine) as session:
        stored = session.scalar(select(TwoFactorCode))
        assert stored is not None
        assert stored.code_hash != sent_codes[0]
        assert stored.expires_at - stored.created_at == CODE_VALIDITY


def test_valid_code_is_accepted_once():
    create_user()
    sent_codes: list[str] = []

    with patch(
        "app.services.auth.send_two_factor_code",
        side_effect=lambda recipient, code: sent_codes.append(code),
    ):
        client.post(
            "/auth/login",
            json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
        )

    response = client.post(
        "/auth/2fa/verify",
        json={"email": "joao@example.com", "code": sent_codes[0]},
    )
    repeated = client.post(
        "/auth/2fa/verify",
        json={"email": "joao@example.com", "code": sent_codes[0]},
    )

    assert response.json() == {"authenticated": True}
    assert repeated.status_code == 401


def test_incorrect_code_is_rejected():
    create_user()
    with patch("app.services.auth.send_two_factor_code"):
        client.post(
            "/auth/login",
            json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
        )

    response = client.post(
        "/auth/2fa/verify",
        json={"email": "joao@example.com", "code": "000000"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Código de verificação inválido."


def test_expired_code_is_rejected():
    create_user()
    with patch("app.services.auth.send_two_factor_code"):
        client.post(
            "/auth/login",
            json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
        )
    with Session(engine) as session:
        stored = session.scalar(select(TwoFactorCode))
        assert stored is not None
        stored.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()

    response = client.post(
        "/auth/2fa/verify",
        json={"email": "joao@example.com", "code": "000000"},
    )

    assert response.status_code == 401


def test_new_code_invalidates_previous_code():
    create_user()
    sent_codes: list[str] = []
    with patch(
        "app.services.auth.send_two_factor_code",
        side_effect=lambda recipient, code: sent_codes.append(code),
    ):
        login = {"email": "joao@example.com", "senha": "SenhaSegura123!"}
        client.post("/auth/login", json=login)
        client.post("/auth/login", json=login)

    previous = client.post(
        "/auth/2fa/verify",
        json={"email": "joao@example.com", "code": sent_codes[0]},
    )
    current = client.post(
        "/auth/2fa/verify",
        json={"email": "joao@example.com", "code": sent_codes[1]},
    )

    assert previous.status_code == 401
    assert current.json() == {"authenticated": True}


def test_inactive_user_cannot_request_code():
    create_user(status="INATIVO")

    response = client.post(
        "/auth/login",
        json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
    )

    assert response.status_code == 401


def test_code_is_not_exposed_in_api_response_or_logs(caplog):
    create_user()
    with patch("app.services.auth.send_two_factor_code") as send_email:
        response = client.post(
            "/auth/login",
            json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
        )

    code = send_email.call_args.args[1]
    assert "code" not in response.json()
    assert code not in caplog.text
    assert code not in response.text
    assert hash_code(code) not in response.text