import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models.hemocentro import Base
from app.models.usuario import Usuario
from app.security.password import hash_password
from tests.session_helpers import auth_headers


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)


def override_get_db():
    with Session(engine) as session:
        yield session


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_test_database():
    app.dependency_overrides[get_db] = override_get_db
    with Session(engine) as session:
        session.execute(Base.metadata.tables["auth_sessions"].delete())
        session.execute(Base.metadata.tables["audit_logs"].delete())
        session.execute(Base.metadata.tables["hemocentros"].delete())
        session.execute(Base.metadata.tables["usuarios"].delete())
        session.add(
            Usuario(
                nome="Joao Silva",
                cpf="12345678901",
                email="joao@example.com",
                senha_hash=hash_password("SenhaSegura123!"),
                perfil="ADMINISTRADOR",
                status="ATIVO",
            )
        )
        session.commit()
    yield
    app.dependency_overrides.clear()


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
        headers=auth_headers(engine),
    )

    response = client.get("/hemocentros", headers=auth_headers(engine))

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_hemocentro():
    created = client.post(
        "/hemocentros",
        json=payload(),
        headers=auth_headers(engine),
    ).json()

    response = client.get(
        f"/hemocentros/{created['id']}",
        headers=auth_headers(engine),
    )

    assert response.status_code == 200
    assert response.json() == created


def test_create_hemocentro():
    response = client.post(
        "/hemocentros",
        json=payload(),
        headers=auth_headers(engine),
    )

    assert response.status_code == 201
    assert response.json()["nome"] == "Hemocentro Central"
    assert set(response.json()) == {"id", "nome", "endereco", "telefone", "status"}


def change_profile(perfil: str) -> None:
    with Session(engine) as session:
        usuario = session.scalar(select(Usuario).where(Usuario.email == "joao@example.com"))
        assert usuario is not None
        usuario.perfil = perfil
        session.commit()


def test_nurse_can_create_hemocentro_without_changing_institution():
    original = client.post("/hemocentros", json=payload("Unidade original"), headers=auth_headers(engine)).json()
    change_profile("ENFERMEIRO")
    with Session(engine) as session:
        usuario = session.scalar(select(Usuario).where(Usuario.email == "joao@example.com"))
        usuario.hemocentro_id = original["id"]
        session.commit()
    headers = auth_headers(engine)

    response = client.post("/hemocentros", json=payload(), headers=headers)

    assert response.status_code == 201
    assert response.json() == client.get(f"/hemocentros/{response.json()['id']}", headers=headers).json()
    with Session(engine) as session:
        usuario = session.scalar(select(Usuario).where(Usuario.email == "joao@example.com"))
        assert usuario.hemocentro_id == original["id"]


@pytest.mark.parametrize("perfil", ["DOADOR", "MEDICO", "RECEPCIONISTA", "RESPONSAVEL_HEMOCENTRO"])
def test_other_profiles_cannot_create_hemocentro(perfil: str):
    change_profile(perfil)

    response = client.post("/hemocentros", json=payload(), headers=auth_headers(engine))

    assert response.status_code == 403
    assert client.get("/hemocentros", headers=auth_headers(engine)).json() == []


def test_unauthenticated_user_cannot_create_hemocentro():
    response = client.post("/hemocentros", json=payload())

    assert response.status_code == 401


def test_inactive_nurse_cannot_create_hemocentro():
    change_profile("ENFERMEIRO")
    headers = auth_headers(engine)
    with Session(engine) as session:
        usuario = session.scalar(select(Usuario).where(Usuario.email == "joao@example.com"))
        usuario.status = "INATIVO"
        session.commit()

    response = client.post("/hemocentros", json=payload(), headers=headers)

    assert response.status_code == 401


@pytest.mark.parametrize("method", ["put", "delete"])
def test_nurse_cannot_modify_existing_hemocentro(method: str):
    created = client.post("/hemocentros", json=payload(), headers=auth_headers(engine)).json()
    change_profile("ENFERMEIRO")
    headers = auth_headers(engine)
    kwargs = {"headers": headers}
    if method == "put":
        kwargs["json"] = payload("Nome alterado")

    response = getattr(client, method)(f"/hemocentros/{created['id']}", **kwargs)

    assert response.status_code == 403
    assert client.get(f"/hemocentros/{created['id']}", headers=headers).json() == created


@pytest.mark.parametrize("field,limit", [("nome", 255), ("endereco", 500), ("telefone", 30)])
@pytest.mark.parametrize("invalid", ["blank", "too_long"])
def test_invalid_text_fields(field: str, limit: int, invalid: str):
    data = payload()
    data[field] = "   " if invalid == "blank" else "x" * (limit + 1)

    response = client.post("/hemocentros", json=data, headers=auth_headers(engine))

    assert response.status_code == 422


def test_text_fields_are_trimmed():
    data = {key: f"  {value}  " for key, value in payload().items() if key != "status"}
    data["status"] = "ATIVO"

    response = client.post("/hemocentros", json=data, headers=auth_headers(engine))

    assert response.status_code == 201
    assert {key: response.json()[key] for key in payload()} == payload()


def test_update_hemocentro():
    created = client.post(
        "/hemocentros",
        json=payload(),
        headers=auth_headers(engine),
    ).json()
    updated = payload("Hemocentro Zona Norte")
    updated["status"] = "INATIVO"

    response = client.put(
        f"/hemocentros/{created['id']}",
        json=updated,
        headers=auth_headers(engine),
    )

    assert response.status_code == 200
    assert response.json()["nome"] == "Hemocentro Zona Norte"
    assert response.json()["status"] == "INATIVO"


def test_delete_hemocentro():
    created = client.post(
        "/hemocentros",
        json=payload(),
        headers=auth_headers(engine),
    ).json()

    response = client.delete(
        f"/hemocentros/{created['id']}",
        headers=auth_headers(engine),
    )

    assert response.status_code == 204
    assert client.get(
        f"/hemocentros/{created['id']}",
        headers=auth_headers(engine),
    ).status_code == 404


def test_invalid_status():
    invalid = payload()
    invalid["status"] = "PENDENTE"

    response = client.post(
        "/hemocentros",
        json=invalid,
        headers=auth_headers(engine),
    )

    assert response.status_code == 422


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_missing_hemocentro(method: str):
    request = getattr(client, method)
    kwargs = {"json": payload(), "headers": auth_headers(engine)} if method == "put" else {"headers": auth_headers(engine)}

    response = request("/hemocentros/999", **kwargs)

    assert response.status_code == 404