import pytest
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


@pytest.fixture(autouse=True)
def clean_database():
    with Session(engine) as session:
        session.execute(Base.metadata.tables["hemocentros"].delete())
        session.commit()


def payload(name: str = "Hemocentro Central") -> dict[str, str]:
    return {
        "nome": name,
        "endereco": "Av. da Saúde, 100",
        "telefone": "1133334444",
        "status": "ATIVO",
    }


def test_list_hemocentros():
    client.post(
        "/hemocentros",
        json=payload(),
        headers={"x-user-email": "joao@example.com"},
    )

    response = client.get("/hemocentros", headers={"x-user-email": "joao@example.com"})

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_hemocentro():
    created = client.post(
        "/hemocentros",
        json=payload(),
        headers={"x-user-email": "joao@example.com"},
    ).json()

    response = client.get(
        f"/hemocentros/{created['id']}",
        headers={"x-user-email": "joao@example.com"},
    )

    assert response.status_code == 200
    assert response.json() == created


def test_create_hemocentro():
    response = client.post(
        "/hemocentros",
        json=payload(),
        headers={"x-user-email": "joao@example.com"},
    )

    assert response.status_code == 201
    assert response.json()["nome"] == "Hemocentro Central"
    assert set(response.json()) == {"id", "nome", "endereco", "telefone", "status"}


def test_update_hemocentro():
    created = client.post(
        "/hemocentros",
        json=payload(),
        headers={"x-user-email": "joao@example.com"},
    ).json()
    updated = payload("Hemocentro Zona Norte")
    updated["status"] = "INATIVO"

    response = client.put(
        f"/hemocentros/{created['id']}",
        json=updated,
        headers={"x-user-email": "joao@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["nome"] == "Hemocentro Zona Norte"
    assert response.json()["status"] == "INATIVO"


def test_delete_hemocentro():
    created = client.post(
        "/hemocentros",
        json=payload(),
        headers={"x-user-email": "joao@example.com"},
    ).json()

    response = client.delete(
        f"/hemocentros/{created['id']}",
        headers={"x-user-email": "joao@example.com"},
    )

    assert response.status_code == 204
    assert client.get(
        f"/hemocentros/{created['id']}",
        headers={"x-user-email": "joao@example.com"},
    ).status_code == 404


def test_invalid_status():
    invalid = payload()
    invalid["status"] = "PENDENTE"

    response = client.post("/hemocentros", json=invalid)

    assert response.status_code == 422


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_missing_hemocentro(method: str):
    request = getattr(client, method)
    kwargs = {"json": payload(), "headers": {"x-user-email": "joao@example.com"}} if method == "put" else {"headers": {"x-user-email": "joao@example.com"}}

    response = request("/hemocentros/999", **kwargs)

    assert response.status_code == 404