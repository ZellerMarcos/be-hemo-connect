import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app
from app.models import Agendamento, Hemocentro, Usuario
from app.models.hemocentro import Base
from app.security.password import hash_password
from app.security.session import issue_session
from app.security.session import utcnow
from tests.test_agenda import book, change_body, config_payload, slots


@pytest.fixture()
def postgres_context():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Defina TEST_POSTGRES_URL para validar concorrencia em PostgreSQL isolado.")
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    admin_engine = create_engine(url)
    schema = f"agenda_test_{uuid4().hex}"
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        headers = {}
        ids = {}
        with Session(engine) as db:
            db.add(Hemocentro(id=1, nome="Unidade de teste", endereco="Endereco", telefone="123", status="ATIVO"))
            db.flush()
            password = hash_password("SenhaSomenteDeTeste123!")
            for index, (name, profile) in enumerate([
                ("doador", "DOADOR"), ("outro_doador", "DOADOR"),
                ("admin", "ADMINISTRADOR"), ("recepcao", "RECEPCIONISTA"),
            ], 1):
                user = Usuario(nome=name, cpf=f"{index:011d}", email=f"{name}@example.com",
                               perfil=profile, status="ATIVO", senha_hash=password,
                               hemocentro_id=1 if name == "recepcao" else None)
                db.add(user)
                db.flush()
                ids[name] = user.id
                headers[name] = {"Authorization": f"Bearer {issue_session(db, user)}"}

        def override():
            with Session(engine) as db:
                yield db

        app.dependency_overrides[get_db] = override
        with TestClient(app) as client:
            response = client.put("/hemocentros/1/agenda", headers=headers["admin"],
                                  json=config_payload(versao=0))
            assert response.status_code == 200, response.text
            yield client, engine, headers, ids
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def simultaneous(first, second):
    barrier = Barrier(2)

    def run(action):
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run, action) for action in (first, second)]
        return [future.result(timeout=30) for future in futures]


def test_postgres_ultima_vaga_nao_e_vendida_duas_vezes(postgres_context):
    slot = slots(postgres_context)[0]
    responses = simultaneous(
        lambda: book(postgres_context, slot["id"]),
        lambda: book(postgres_context, slot["id"], donor="outro_doador"),
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert slots(postgres_context)[0]["vagas_disponiveis"] == 0


def test_postgres_cancelamento_e_recepcao_tem_uma_transicao(postgres_context):
    client, engine, headers, _ = postgres_context
    slot = slots(postgres_context)[0]
    reservation = book(postgres_context, slot["id"]).json()
    responses = simultaneous(
        lambda: client.post(f"/agendamentos/{reservation['id']}/cancelar",
                            headers=headers["doador"], json=change_body(reservation)),
        lambda: client.post(f"/recepcao/agendamentos/{reservation['id']}/receber",
                            headers=headers["recepcao"], json={"versao": reservation["versao"]}),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    with Session(engine) as db:
        status = db.get(Agendamento, reservation["id"]).status
    assert slots(postgres_context)[0]["vagas_disponiveis"] == (1 if status == "CANCELADO" else 0)


def test_postgres_remarcacao_disputa_vaga_sem_perder_original(postgres_context):
    client, engine, headers, _ = postgres_context
    available = slots(postgres_context)
    original = book(postgres_context, available[0]["id"]).json()
    responses = simultaneous(
        lambda: client.post(f"/agendamentos/{original['id']}/remarcar", headers=headers["doador"],
                            json={**change_body(original), "horario_id": available[1]["id"]}),
        lambda: book(postgres_context, available[1]["id"], donor="outro_doador"),
    )
    assert sorted(response.status_code for response in responses) in ([200, 409], [201, 409])
    with Session(engine) as db:
        current = db.get(Agendamento, original["id"])
        assert current.horario_id == (available[1]["id"] if responses[0].status_code == 200 else available[0]["id"])
        occupants = db.scalars(select(Agendamento).where(
            Agendamento.horario_id == available[1]["id"], Agendamento.status != "CANCELADO",
        )).all()
        assert len(occupants) == 1


def test_postgres_mudanca_de_capacidade_nao_invalida_reserva(postgres_context):
    client, _, headers, _ = postgres_context
    assert client.put("/hemocentros/1/agenda", headers=headers["admin"],
                      json=config_payload(versao=1, capacidade=2)).status_code == 200
    slot = slots(postgres_context)[0]
    assert book(postgres_context, slot["id"]).status_code == 201
    responses = simultaneous(
        lambda: client.put("/hemocentros/1/agenda", headers=headers["admin"],
                            json=config_payload(versao=2, capacidade=1)),
        lambda: book(postgres_context, slot["id"], donor="outro_doador"),
    )
    assert sorted(response.status_code for response in responses) in ([200, 409], [201, 409])


def test_postgres_remarcacao_e_recepcao_nao_usam_reserva_desatualizada(postgres_context):
    client, _, headers, _ = postgres_context
    available = slots(postgres_context)
    original = book(postgres_context, available[0]["id"]).json()
    responses = simultaneous(
        lambda: client.post(f"/agendamentos/{original['id']}/remarcar", headers=headers["doador"],
                            json={**change_body(original), "horario_id": available[1]["id"]}),
        lambda: client.post(f"/recepcao/agendamentos/{original['id']}/receber", headers=headers["recepcao"],
                            json={"versao": original["versao"]}),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]


def test_postgres_migration_idempotente(postgres_context):
    client, engine, headers, ids = postgres_context
    # Apenas no schema temporario do fixture: reproduz a estrutura anterior.
    with engine.begin() as connection:
        for column in ("horario_id", "chave_requisicao", "versao", "cancelavel_ate", "remarcavel_ate", "cancelado_em"):
            connection.exec_driver_sql(f"ALTER TABLE agendamentos DROP COLUMN {column} CASCADE")
        day = (utcnow() + timedelta(days=1)).date()
        start = datetime.combine(day, datetime.min.time()).replace(hour=12)
        connection.exec_driver_sql(
            "INSERT INTO agendamentos (doador_id, hemocentro_id, agendado_em, status, respostas_pre_triagem, criado_em) "
            "VALUES (%s, 1, %s, 'AGENDADO', '[]', %s)",
            (ids["doador"], start, utcnow()),
        )
    script = (Path(__file__).resolve().parents[1] / "sql" / "003_agenda_reservas.sql").read_text(encoding="utf-8")
    for _ in range(2):
        with engine.connect() as connection:
            connection.exec_driver_sql(script)
    legacy = client.get("/agendamentos/me", headers=headers["doador"]).json()[0]
    assert legacy["horario_id"] is None and legacy["versao"] == 1 and legacy["pode_cancelar"]
    assert client.put("/hemocentros/1/agenda", headers=headers["admin"],
                      json=config_payload(versao=1)).status_code == 200
    assert slots(postgres_context)
