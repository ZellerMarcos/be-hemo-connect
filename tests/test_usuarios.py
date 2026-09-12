import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models.hemocentro import Base
from app.models.usuario import Usuario
from app.security.password import hash_password, verify_password


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
        session.execute(Base.metadata.tables["usuarios"].delete())
        session.commit()


def override_get_db():
    with Session(engine) as session:
        yield session


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_dependency_overrides():
    # Isola o override por teste para evitar interferencia de outros modulos de teste.
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


def create_user(**overrides: object) -> dict[str, object]:
    response = client.post("/usuarios", json=payload(**overrides))
    assert response.status_code == 201
    return response.json()


def test_list_users():
    create_user()

    response = client.get("/usuarios", headers={"x-user-email": "joao@example.com"})

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_existing_user():
    created = create_user()

    response = client.get(
        f"/usuarios/{created['id']}",
        headers={"x-user-email": "joao@example.com"},
    )

    assert response.status_code == 200
    assert response.json() == created


def test_get_missing_user():
    assert client.get("/usuarios/999", headers={"x-user-email": "joao@example.com"}).status_code == 401


def test_create_user():
    response = client.post("/usuarios", json=payload())

    assert response.status_code == 201
    assert set(response.json()) == {
        "id",
        "nome",
        "cpf",
        "email",
        "perfil",
        "status",
        "hemocentro_id",
    }
    assert "senha_hash" not in response.json()


def test_update_user():
    created = create_user()
    update = payload(
        nome="Maria Silva",
        cpf="10987654321",
        email="maria@example.com",
        perfil="ENFERMEIRO",
        status="INATIVO",
    )
    update.pop("senha")

    response = client.put(
        f"/usuarios/{created['id']}",
        json=update,
        headers={"x-user-email": "joao@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["nome"] == "Maria Silva"
    assert response.json()["perfil"] == "ENFERMEIRO"
    assert "senha_hash" not in response.json()


def test_delete_user():
    created = create_user()

    response = client.delete(
        f"/usuarios/{created['id']}",
        headers={"x-user-email": "joao@example.com"},
    )

    assert response.status_code == 204
    assert client.get(
        f"/usuarios/{created['id']}",
        headers={"x-user-email": "joao@example.com"},
    ).status_code == 401


def test_invalid_cpf():
    assert client.post("/usuarios", json=payload(cpf="123")).status_code == 422


def test_invalid_email():
    assert client.post("/usuarios", json=payload(email="not-an-email")).status_code == 422


def test_invalid_profile():
    assert client.post("/usuarios", json=payload(perfil="PACIENTE")).status_code == 422


def test_invalid_status():
    assert client.post("/usuarios", json=payload(status="PENDENTE")).status_code == 422


def test_duplicate_cpf():
    create_user()

    response = client.post("/usuarios", json=payload(email="other@example.com"))

    assert response.status_code == 409


def test_duplicate_email():
    create_user()

    response = client.post("/usuarios", json=payload(cpf="10987654321"))

    assert response.status_code == 409


def test_password_is_hashed_and_not_stored_in_plain_text():
    create_user()

    with Session(engine) as session:
        stored_hash = session.scalar(select(Usuario.senha_hash))

    assert stored_hash != "SenhaSegura123!"
    assert stored_hash.startswith("$argon2id$")


def test_password_verification():
    stored_hash = hash_password("SenhaSegura123!")

    assert verify_password("SenhaSegura123!", stored_hash) is True
    assert verify_password("SenhaErrada!", stored_hash) is False


def test_hashes_for_same_password_are_different():
    first_hash = hash_password("SenhaSegura123!")
    second_hash = hash_password("SenhaSegura123!")

    assert first_hash != second_hash


def test_login_with_correct_password():
    created = create_user()

    with patch("app.services.auth.send_two_factor_code"):
        response = client.post(
            "/auth/login",
            json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
        )

    assert response.status_code == 200
    assert response.json() == {"requires_2fa": True}
    assert created["id"] is not None


def test_login_with_incorrect_password():
    create_user()

    response = client.post(
        "/auth/login",
        json={"email": "joao@example.com", "senha": "SenhaErrada!"},
    )

    assert response.status_code == 401
    assert response.json()["detail"].startswith("E-mail ou senha inválidos.")


def test_login_with_unknown_email():
    response = client.post(
        "/auth/login",
        json={"email": "ausente@example.com", "senha": "SenhaSegura123!"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha inválidos."


def test_inactive_user_cannot_login():
    create_user(status="INATIVO")

    response = client.post(
        "/auth/login",
        json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha inválidos."


def test_login_response_does_not_expose_password_fields():
    create_user()

    with patch("app.services.auth.send_two_factor_code"):
        response = client.post(
            "/auth/login",
            json={"email": "joao@example.com", "senha": "SenhaSegura123!"},
        )

    assert "senha" not in response.json()
    assert "senha_hash" not in response.json()


def test_create_user_requires_explicit_consent():
    response = client.post(
        "/usuarios",
        json=payload(consentimento_aceito=False),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "O consentimento explicito e obrigatorio para concluir o cadastro."