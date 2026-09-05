import os
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("APP_ENV", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models.hemocentro import Base
from app.models.password_reset_token import PasswordResetToken
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
        session.execute(Base.metadata.tables["password_reset_tokens"].delete())
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

    assert response.json() == {"authenticated": True, "nome": "Joao Silva"}
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
    assert current.json() == {"authenticated": True, "nome": "Joao Silva"}


def test_inactive_user_cannot_request_code():
    create_user(status="INATIVO")

    response = client.post(
        "/auth/login",
        json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
    )

    assert response.status_code == 401


def test_user_can_request_password_reset_link():
    create_user()
    sent_links: list[str] = []

    def capture_reset_link(recipient: str, reset_url: str) -> None:
        sent_links.append(reset_url)

    with patch("app.services.auth.send_password_reset_link", side_effect=capture_reset_link):
        response = client.post(
            "/auth/forgot-password",
            json={"email": "joao@example.com"},
        )

    assert response.status_code == 200
    assert response.json() == {"sent": True}
    assert len(sent_links) == 1
    assert "token=" in sent_links[0]


def test_password_reset_token_updates_password():
    create_user()
    sent_links: list[str] = []

    with patch(
        "app.services.auth.send_password_reset_link",
        side_effect=lambda recipient, reset_url: sent_links.append(reset_url),
    ):
        client.post(
            "/auth/forgot-password",
            json={"email": "joao@example.com"},
        )

    token = sent_links[0].split("token=")[-1]
    response = client.post(
        "/auth/reset-password",
        json={"token": token, "senha": "NovaSenha123!"},
    )

    assert response.status_code == 200
    assert response.json() == {"reset": True}

    login_response = client.post(
        "/auth/login",
        json={"email": "joao@example.com", "senha": "NovaSenha123!"},
    )
    assert login_response.status_code == 200
    assert login_response.json() == {"requires_2fa": True}


def test_invalid_password_reset_token_is_rejected():
    response = client.post(
        "/auth/reset-password",
        json={"token": "invalid-token", "senha": "NovaSenha123!"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Token de redefinição inválido ou expirado."


def test_expired_password_reset_token_is_rejected():
    create_user()
    sent_links: list[str] = []

    with patch(
        "app.services.auth.send_password_reset_link",
        side_effect=lambda recipient, reset_url: sent_links.append(reset_url),
    ):
        client.post("/auth/forgot-password", json={"email": "joao@example.com"})

    with Session(engine) as session:
        stored = session.scalar(select(PasswordResetToken))
        assert stored is not None
        stored.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()

    response = client.post(
        "/auth/reset-password",
        json={"token": sent_links[0].split("token=")[-1], "senha": "NovaSenha123!"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Token de redefinição inválido ou expirado."


def test_password_reset_token_cannot_be_reused():
    create_user()
    sent_links: list[str] = []

    with patch(
        "app.services.auth.send_password_reset_link",
        side_effect=lambda recipient, reset_url: sent_links.append(reset_url),
    ):
        client.post("/auth/forgot-password", json={"email": "joao@example.com"})

    token = sent_links[0].split("token=")[-1]
    first_response = client.post(
        "/auth/reset-password",
        json={"token": token, "senha": "NovaSenha123!"},
    )
    second_response = client.post(
        "/auth/reset-password",
        json={"token": token, "senha": "OutraSenha123!"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 400


def test_password_reset_request_is_registered_in_log(caplog):
    create_user()

    with caplog.at_level("INFO", logger="app.services.auth"), patch(
        "app.services.auth.send_password_reset_link"
    ):
        response = client.post(
            "/auth/forgot-password",
            json={"email": "joao@example.com"},
        )

    assert response.status_code == 200
    assert "Solicitacao de recuperacao de senha registrada" in caplog.text
    assert "joao@example.com" in caplog.text


def test_user_session_expires_after_45_minutes_of_inactivity():
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
    assert response.status_code == 200

    with Session(engine) as session:
        usuario = session.scalar(select(Usuario).where(Usuario.email == "joao@example.com"))
        assert usuario is not None
        usuario.last_activity_at = datetime.utcnow() - timedelta(minutes=46)
        session.commit()

    response = client.get(
        "/usuarios",
        headers={"x-user-email": "joao@example.com"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Sessão expirada por inatividade."


def test_user_is_blocked_after_five_failed_logins_in_15_minutes():
    create_user()

    for _ in range(5):
        response = client.post(
            "/auth/login",
            json={"email": "joao@example.com", "senha": "SenhaInvalida123!"},
        )
        assert response.status_code == 401

    response = client.post(
        "/auth/login",
        json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Conta temporariamente bloqueada. Tente novamente em 1 hora."


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