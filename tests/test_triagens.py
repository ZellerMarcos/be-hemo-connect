from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app
from app.models import Agendamento, AuditLog, AuthSession, Hemocentro, Triagem, Usuario
from app.models.hemocentro import Base
from app.security.audit import verificar_integridade
from app.security.password import hash_password
from app.security.session import issue_session, utcnow


@pytest.fixture()
def context(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'triagens.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    headers = {}
    ids = {}
    with Session(engine) as db:
        db.add_all([Hemocentro(id=1, nome="Centro", endereco="Endereço", telefone="123", status="ATIVO"),
                    Hemocentro(id=2, nome="Outra unidade", endereco="Endereço", telefone="456", status="ATIVO")])
        db.flush()
        password_hash = hash_password("SenhaSegura123!")
        for index, (key, perfil, centro) in enumerate([
            ("doador", "DOADOR", None), ("outro_doador", "DOADOR", None),
            ("enfermeiro", "ENFERMEIRO", 1), ("outro_enfermeiro", "ENFERMEIRO", 1),
            ("externo", "ENFERMEIRO", 2), ("sem_vinculo", "ENFERMEIRO", None),
            ("recepcao", "RECEPCIONISTA", 1), ("medico", "MEDICO", 1),
            ("admin", "ADMINISTRADOR", None),
        ], 1):
            usuario = Usuario(nome=key, cpf=f"{index:011d}", email=f"{key}@example.com",
                              senha_hash=password_hash, perfil=perfil, status="ATIVO", hemocentro_id=centro)
            db.add(usuario)
            db.flush()
            ids[key] = usuario.id
            headers[key] = {"Authorization": f"Bearer {issue_session(db, usuario)}"}

    def override():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, engine, headers, ids
    app.dependency_overrides.clear()
    engine.dispose()


def agendar(context, centro=1, donor="doador"):
    client, _, headers, _ = context
    response = client.post("/agendamentos", headers=headers[donor], json={
        "hemocentro_id": centro,
        "agendado_em": (utcnow() + timedelta(days=1)).isoformat() + "Z",
        "respostas_pre_triagem": [{"pergunta": "Pergunta institucional", "resposta": "Resposta registrada"}],
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def receber(context):
    client, _, headers, _ = context
    agenda_id = agendar(context)
    assert client.post(f"/recepcao/agendamentos/{agenda_id}/receber",
                       headers=headers["recepcao"]).status_code == 200
    return agenda_id


@pytest.mark.parametrize("resultado", ["APTO", "INAPTO", "ENCAMINHADO_MEDICO"])
def test_fluxo_completo(context, resultado):
    client, engine, headers, _ = context
    agenda_id = receber(context)
    stats = client.get("/triagens/indicadores", headers=headers["enfermeiro"]).json()
    assert stats == {"pendentes": 1, "em_atendimento": 0, "concluidas": 0, "encaminhadas_medico": 0}
    fila = client.get("/triagens", headers=headers["enfermeiro"]).json()
    assert fila["total"] == 1 and fila["itens"][0]["status"] == "AGUARDANDO_TRIAGEM"
    assert "cpf" not in fila["itens"][0] and "*" in fila["itens"][0]["cpf_mascarado"]
    inicio = client.post(f"/triagens/{agenda_id}/iniciar", headers=headers["enfermeiro"])
    assert inicio.status_code == 200, inicio.text
    assert inicio.json()["agendamento"]["status"] == "EM_TRIAGEM"
    assert inicio.json()["pre_triagem"] == [{"pergunta": "Pergunta institucional", "resposta": "Resposta registrada"}]
    saved = client.put(f"/triagens/{agenda_id}", headers=headers["enfermeiro"],
                       json={"observacoes": "Avaliação registrada", "versao": 1})
    assert saved.status_code == 200 and saved.json()["avaliacao"]["versao"] == 2
    finalized = client.post(f"/triagens/{agenda_id}/finalizar", headers=headers["enfermeiro"],
                            json={"observacoes": "Avaliação revisada", "versao": 2, "resultado": resultado})
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["agendamento"]["status"] == resultado
    assert finalized.json()["avaliacao"]["finalizada_em"]
    assert finalized.json()["historico"][0]["resultado"] == resultado
    assert client.get("/historico/me", headers=headers["doador"]).json()[0]["tipo"] == "Triagem"
    with Session(engine) as db:
        assert db.scalar(select(Triagem.observacoes)) == "Avaliação revisada"
        events = db.scalars(select(AuditLog).where(AuditLog.event_type.like("TRIAGEM_%"))).all()
        assert len(events) == 3
        assert all("Avaliação" not in str(event.metadata_json) for event in events)
        assert all(event.metadata_json["atendimento_id"] == agenda_id for event in events)
        assert verificar_integridade(db) == (True, None)


@pytest.mark.parametrize("role", ["doador", "medico", "recepcao", "admin"])
@pytest.mark.parametrize("method,path,body", [
    ("get", "/triagens", None), ("get", "/triagens/indicadores", None),
    ("get", "/triagens/1", None), ("post", "/triagens/1/iniciar", None),
    ("put", "/triagens/1", {"observacoes": "Texto", "versao": 1}),
    ("post", "/triagens/1/finalizar", {"observacoes": "Texto", "versao": 1, "resultado": "APTO"}),
])
def test_outros_perfis_bloqueados(context, role, method, path, body):
    client, _, headers, _ = context
    kwargs = {"headers": headers[role]}
    if body is not None:
        kwargs["json"] = body
    assert getattr(client, method)(path, **kwargs).status_code == 403


def test_isolamento_por_hemocentro_e_por_doador(context):
    client, _, headers, _ = context
    agenda_id = receber(context)
    assert client.get(f"/triagens/{agenda_id}", headers=headers["externo"]).status_code == 404
    assert client.post(f"/triagens/{agenda_id}/iniciar", headers=headers["externo"]).status_code == 404
    assert client.get("/triagens", headers=headers["externo"]).json()["total"] == 0
    assert client.get("/triagens", headers=headers["sem_vinculo"]).status_code == 403
    assert client.get("/agendamentos/me", headers=headers["outro_doador"]).json() == []
    assert client.post(f"/recepcao/agendamentos/{agendar(context, centro=2)}/receber",
                       headers=headers["recepcao"]).status_code == 404


def test_nao_permite_falsificar_identidade(context):
    client, _, headers, ids = context
    assert client.get("/triagens", headers={"X-User-Email": "enfermeiro@example.com"}).status_code == 401
    assert client.get("/triagens", headers={"Authorization": "Bearer inventado"}).status_code == 401
    assert client.get("/triagens", headers={**headers["doador"], "X-User-Email": "enfermeiro@example.com"}).status_code == 403
    assert client.get(f"/usuarios/{ids['enfermeiro']}", headers=headers["doador"]).status_code == 403
    payload = {"nome": "Novo", "cpf": "12345678901", "email": "novo@example.com",
               "senha": "SenhaSegura123!", "perfil": "ENFERMEIRO", "status": "ATIVO",
               "coren_numero": "123456", "coren_uf": "SP",
               "hemocentro_id": 1, "consentimento_aceito": True,
               "consentimento_versao": "v1", "consentimento_finalidades": ["cadastro"]}
    assert client.post("/usuarios", json=payload).status_code == 401
    assert client.post("/usuarios", json=payload, headers=headers["doador"]).status_code == 403
    assert client.post("/usuarios", json=payload, headers=headers["admin"]).status_code == 201


def test_concorrencia_inicio(context):
    client, engine, headers, _ = context
    agenda_id = receber(context)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(client.post, f"/triagens/{agenda_id}/iniciar", headers=headers[role])
                   for role in ("enfermeiro", "outro_enfermeiro")]
        statuses = sorted(future.result().status_code for future in futures)
    assert statuses == [200, 409]
    with Session(engine) as db:
        assert len(db.scalars(select(Triagem)).all()) == 1


def test_versao_autoria_e_finalizacao_unica(context):
    client, _, headers, _ = context
    agenda_id = receber(context)
    path = f"/triagens/{agenda_id}"
    assert client.post(path + "/finalizar", headers=headers["enfermeiro"],
                       json={"observacoes": "Texto", "versao": 1, "resultado": "APTO"}).status_code == 409
    client.post(path + "/iniciar", headers=headers["enfermeiro"])
    assert client.put(path, headers=headers["outro_enfermeiro"],
                      json={"observacoes": "Texto", "versao": 1}).status_code == 403
    assert client.put(path, headers=headers["enfermeiro"],
                      json={"observacoes": "Texto", "versao": 2}).status_code == 409
    assert client.put(path, headers=headers["enfermeiro"],
                      json={"observacoes": " ", "versao": 1}).status_code == 422
    assert client.put(path, headers=headers["enfermeiro"],
                      json={"observacoes": "Texto", "versao": 1, "pre_triagem": []}).status_code == 422
    body = {"observacoes": "Texto", "versao": 1, "resultado": "APTO"}
    assert client.post(path + "/finalizar", headers=headers["enfermeiro"], json=body).status_code == 200
    assert client.post(path + "/finalizar", headers=headers["enfermeiro"], json=body).status_code == 409


def test_filtros_paginacao_e_estado_vazio(context):
    client, _, headers, _ = context
    assert client.get("/triagens", headers=headers["enfermeiro"]).json()["itens"] == []
    receber(context)
    receber(context)
    response = client.get("/triagens?pagina=2&tamanho=1&busca=doador&status=AGUARDANDO_TRIAGEM",
                          headers=headers["enfermeiro"]).json()
    assert response["total"] == 2 and len(response["itens"]) == 1 and response["pagina"] == 2
    assert client.get("/triagens?busca=00000000001", headers=headers["enfermeiro"]).json()["total"] == 2
    assert client.get("/triagens?busca=ausente", headers=headers["enfermeiro"]).json()["total"] == 0
    assert client.get("/triagens?inicio=2026-10-10&fim=2026-10-01",
                      headers=headers["enfermeiro"]).status_code == 422
    assert client.get("/triagens?status=INVENTADO", headers=headers["enfermeiro"]).status_code == 422


def test_sessao_2fa_logout_expiracao_e_reset(context):
    client, engine, headers, ids = context
    with patch("app.services.auth.send_two_factor_code") as send:
        assert client.post("/auth/login", json={"email": "enfermeiro@example.com",
                                               "senha": "SenhaSegura123!"}).json() == {"requires_2fa": True}
    response = client.post("/auth/2fa/verify", json={"email": "enfermeiro@example.com",
                                                  "code": send.call_args.args[1]})
    assert response.status_code == 200
    assert response.json()["usuario"]["perfil"] == "ENFERMEIRO"
    assert response.json()["usuario"]["id"] == ids["enfermeiro"]
    login_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/auth/me", headers=login_headers).status_code == 200
    assert client.post("/auth/logout", headers=login_headers).status_code == 200
    assert client.get("/auth/me", headers=login_headers).status_code == 401
    with Session(engine) as db:
        session = db.scalar(select(AuthSession).where(AuthSession.usuario_id == ids["doador"]))
        session.last_activity_at = utcnow() - timedelta(minutes=46)
        db.commit()
    assert client.get("/auth/me", headers=headers["doador"]).status_code == 401
    with patch("app.services.auth.send_password_reset_email") as send:
        client.post("/auth/forgot-password", json={"email": "enfermeiro@example.com"})
    token = send.call_args.args[1].split("token=")[-1]
    assert client.post("/auth/reset-password", json={"token": token, "senha": "OutraSenha123!"}).status_code == 200
    assert client.get("/triagens", headers=headers["enfermeiro"]).status_code == 401


def test_finalizacao_concorrente(context):
    client, engine, headers, _ = context
    agenda_id = receber(context)
    client.post(f"/triagens/{agenda_id}/iniciar", headers=headers["enfermeiro"])
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(
            client.post, f"/triagens/{agenda_id}/finalizar", headers=headers["enfermeiro"],
            json={"observacoes": "Registro único", "versao": 1, "resultado": result},
        ) for result in ("APTO", "INAPTO")]
        responses = [future.result() for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409]
    with Session(engine) as db:
        agenda = db.get(Agendamento, agenda_id)
        avaliacao = db.scalar(select(Triagem))
        assert agenda.status == avaliacao.resultado
        assert avaliacao.versao == 2


def test_privacidade_inclui_novos_dados_e_revoga_acesso(context):
    client, engine, headers, ids = context
    agenda_id = receber(context)
    with Session(engine) as db:
        usuario = db.get(Usuario, ids["doador"])
        usuario.telefone = "11999999999"
        usuario.tipo_sanguineo = "O+"
        db.commit()
    client.post(f"/triagens/{agenda_id}/iniciar", headers=headers["enfermeiro"])
    client.post(f"/triagens/{agenda_id}/finalizar", headers=headers["enfermeiro"],
                json={"observacoes": "Registro para exportação", "versao": 1, "resultado": "APTO"})
    response = client.get("/privacy/export", headers=headers["doador"])
    assert response.status_code == 200
    data = response.json()["titular"]
    assert data["telefone"] == "11999999999" and data["tipo_sanguineo"] == "O+"
    assert data["atendimentos"][0]["observacoes"] == "Registro para exportação"
    assert data["atendimentos"][0]["pre_triagem"][0]["resposta"] == "Resposta registrada"
    assert "enfermeiro_id" not in data["atendimentos"][0]
    assert client.delete("/privacy/me", headers=headers["doador"]).status_code == 200
    assert client.get("/auth/me", headers=headers["doador"]).status_code == 401
    assert client.get(f"/triagens/{agenda_id}", headers=headers["enfermeiro"]).status_code == 404
    with Session(engine) as db:
        usuario = db.get(Usuario, ids["doador"])
        assert usuario.telefone is None and usuario.tipo_sanguineo is None
        assert db.get(Agendamento, agenda_id).respostas_pre_triagem == []


def test_limite_exato_inatividade(context):
    client, engine, headers, ids = context
    instant = utcnow()
    with Session(engine) as db:
        session = db.scalar(select(AuthSession).where(AuthSession.usuario_id == ids["enfermeiro"]))
        session.last_activity_at = instant - timedelta(minutes=45)
        db.commit()
    with patch("app.security.session.utcnow", return_value=instant):
        assert client.get("/auth/me", headers=headers["enfermeiro"]).status_code == 200
    with patch("app.security.session.utcnow", return_value=instant + timedelta(minutes=45, microseconds=1)):
        assert client.get("/auth/me", headers=headers["enfermeiro"]).status_code == 401


def test_validacao_agendamento_e_recepcao(context):
    client, _, headers, _ = context
    body = {"hemocentro_id": 1, "agendado_em": (utcnow() - timedelta(days=1)).isoformat() + "Z"}
    assert client.post("/agendamentos", headers=headers["doador"], json=body).status_code == 422
    body["agendado_em"] = (utcnow() + timedelta(days=1)).isoformat()
    assert client.post("/agendamentos", headers=headers["doador"], json=body).status_code == 422
    body["agendado_em"] += "Z"
    assert client.post("/agendamentos", headers=headers["enfermeiro"], json=body).status_code == 403
    agenda_id = agendar(context)
    assert client.post(f"/triagens/{agenda_id}/iniciar", headers=headers["enfermeiro"]).status_code == 409
    assert client.post(f"/recepcao/agendamentos/{agenda_id}/receber",
                       headers=headers["enfermeiro"]).status_code == 403
    assert client.post(f"/recepcao/agendamentos/{agenda_id}/receber",
                       headers=headers["recepcao"]).status_code == 200
    assert client.post(f"/recepcao/agendamentos/{agenda_id}/receber",
                       headers=headers["recepcao"]).status_code == 409
