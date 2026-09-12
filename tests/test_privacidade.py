import os
from unittest.mock import patch

os.environ.setdefault("APP_ENV", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models.consentimento import Consentimento
from app.models.hemocentro import Base
from app.models.usuario import Usuario


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def clean_database():
    with Session(engine) as session:
        session.execute(Base.metadata.tables["consentimentos"].delete())
        session.execute(Base.metadata.tables["two_factor_codes"].delete())
        session.execute(Base.metadata.tables["password_reset_tokens"].delete())
        session.execute(Base.metadata.tables["usuarios"].delete())
        session.commit()


def override_get_db():
    with Session(engine) as session:
        yield session


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_dependency_overrides():
    # Isola o override por teste para evitar colisao com outros modulos da suite.
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


def payload(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "nome": "Joao Silva",
        "cpf": "12345678901",
        "email": "joao@example.com",
        "senha": "SenhaSegura123!",
        "perfil": "DOADOR",
        "status": "ATIVO",
        "hemocentro_id": None,
        "consentimento_aceito": True,
        "consentimento_versao": "v1.0",
        "consentimento_finalidades": ["cadastro", "autenticacao", "seguranca"],
    }
    data.update(overrides)
    return data


def create_user() -> None:
    response = client.post("/usuarios", json=payload())
    assert response.status_code == 201


@pytest.fixture()
def authenticated_user() -> dict[str, str]:
    # Prepara um usuario autenticado para exercitar os endpoints de direitos do titular.
    create_user()
    with patch("app.services.auth.send_two_factor_code") as send_email:
        response = client.post(
            "/auth/login",
            json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
        )

    assert response.status_code == 200
    code = send_email.call_args.args[1]
    verify = client.post(
        "/auth/2fa/verify",
        json={"email": "joao@example.com", "code": code},
    )
    assert verify.status_code == 200
    return {"x-user-email": "joao@example.com"}


def test_privacy_me_returns_titular_data(authenticated_user):
    # Consulta principal de dados do titular autenticado.
    response = client.get("/privacy/me", headers=authenticated_user)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "joao@example.com"
    assert len(body["consentimentos"]) == 3


def test_privacy_export_returns_structured_payload(authenticated_user):
    # Exportacao deve retornar dados e timestamp de emissao.
    response = client.get("/privacy/export", headers=authenticated_user)

    assert response.status_code == 200
    body = response.json()
    assert body["titular"]["email"] == "joao@example.com"
    assert body["exportado_em"]


def test_privacy_revoke_consent_updates_latest_consent(authenticated_user):
    # Revoga a finalidade informada e valida persistencia do estado revogado.
    response = client.post(
        "/privacy/consent/revoke",
        headers=authenticated_user,
        json={"finalidade": "seguranca"},
    )

    assert response.status_code == 200
    assert response.json()["revogado"] is True

    with Session(engine) as session:
        consentimento = session.scalar(
            select(Consentimento).where(
                Consentimento.usuario_id == 1,
                Consentimento.finalidade == "seguranca",
            )
        )

    assert consentimento is not None
    assert consentimento.concedido is False
    assert consentimento.revogado_em is not None


def test_privacy_delete_anonymizes_titular_data(authenticated_user):
    # Exclusao LGPD precisa anonimizar dados e desativar acesso da conta.
    response = client.delete("/privacy/me", headers=authenticated_user)

    assert response.status_code == 200
    assert response.json()["excluido"] is True

    with Session(engine) as session:
        usuario = session.scalar(select(Usuario).where(Usuario.id == 1))

    assert usuario is not None
    assert usuario.status == "INATIVO"
    assert usuario.nome == "Titular removido"
    assert usuario.email.endswith("@example.invalid")
    assert usuario.last_activity_at is None
