from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models.hemocentro import Base


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)


def override_get_db():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def payload(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "nome": "Joao Silva",
        "cpf": "12345678901",
        "email": "joao@example.com",
        "senha_hash": "HASH_DE_TESTE",
        "perfil": "DOADOR",
        "status": "ATIVO",
        "hemocentro_id": None,
    }
    data.update(overrides)
    return data


def create_user(**overrides: object) -> dict[str, object]:
    response = client.post("/usuarios", json=payload(**overrides))
    assert response.status_code == 201
    return response.json()


def test_list_users():
    create_user()

    response = client.get("/usuarios")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_existing_user():
    created = create_user()

    response = client.get(f"/usuarios/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_missing_user():
    assert client.get("/usuarios/999").status_code == 404


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
        senha_hash=None,
        perfil="ENFERMEIRO",
        status="INATIVO",
    )
    update.pop("senha_hash")

    response = client.put(f"/usuarios/{created['id']}", json=update)

    assert response.status_code == 200
    assert response.json()["nome"] == "Maria Silva"
    assert response.json()["perfil"] == "ENFERMEIRO"
    assert "senha_hash" not in response.json()


def test_delete_user():
    created = create_user()

    response = client.delete(f"/usuarios/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/usuarios/{created['id']}").status_code == 404


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