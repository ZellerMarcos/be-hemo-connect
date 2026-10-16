from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agendamento, AuditLog
from app.schemas.questionario import QuestionarioSubmission
from app.services.questionario import canonico, validar
from tests.questionario_helpers import questionario_payload
from tests.test_agenda import agenda, slots  # noqa: F401
from tests.test_triagens import context, receber  # noqa: F401


def alterar(data, id, valores):
    data["respostas"] = [item for item in data["respostas"] if item["id"] != id]
    data["respostas"].append({"id": id, "valores": valores})
    return data


def enviar(agenda, data, key=None):
    client, _, headers, _ = agenda
    slot = slots(agenda)[0]
    return client.post("/agendamentos", headers=headers["doador"], json={
        "horario_id": slot["id"], "chave_requisicao": key or str(uuid4()), "questionario": data,
    })


def test_catalogo_versionado_autenticado(context):
    client, _, headers, _ = context
    assert client.get("/questionario-pre-triagem").status_code == 401
    response = client.get("/questionario-pre-triagem", headers=headers["doador"])
    assert response.status_code == 200
    data = response.json()
    assert data["publicado"] is True
    assert data["versao"] == "pre-triagem-v1"
    assert "dados sensíveis" in data["aviso"]
    assert "Instituicao ficticia de teste" in data["aviso"]
    assert len({item["id"] for item in data["perguntas"]}) == len(data["perguntas"])
    assert len(data["confirmacoes"]) == 3
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/questionario-pre-triagem", headers=headers["recepcao"]).status_code == 403


def test_ultima_resposta_isolada_por_doador_unidade_e_versao(agenda):
    client, _, headers, _ = agenda
    empty = client.get("/questionario-pre-triagem/ultima-resposta?hemocentro_id=1",
                       headers=headers["doador"])
    assert empty.status_code == 200
    assert empty.json() == {
        "encontrado": False, "compativel": False, "versao": None,
        "versao_aviso": None, "enviado_em": None, "respostas": [],
    }

    reservation = enviar(agenda, questionario_payload())
    assert reservation.status_code == 201
    own = client.get("/questionario-pre-triagem/ultima-resposta?hemocentro_id=1",
                     headers=headers["doador"])
    assert own.status_code == 200
    assert own.json()["encontrado"] is True and own.json()["compativel"] is True
    assert own.json()["versao"] == "pre-triagem-v1"
    assert own.json()["enviado_em"]
    assert {"id": "peso", "valores": ["70"]} in own.json()["respostas"]

    other_unit = client.get("/questionario-pre-triagem/ultima-resposta?hemocentro_id=2",
                            headers=headers["doador"])
    other_user = client.get("/questionario-pre-triagem/ultima-resposta?hemocentro_id=1",
                            headers=headers["outro_doador"])
    assert other_unit.json()["encontrado"] is False
    assert other_user.json()["encontrado"] is False
    assert client.get("/questionario-pre-triagem/ultima-resposta?hemocentro_id=1",
                      headers=headers["recepcao"]).status_code == 403
    assert own.headers["cache-control"] == "no-store"
    canceled = client.post(f"/agendamentos/{reservation.json()['id']}/cancelar",
                           headers=headers["doador"], json={"versao": 1, "chave_requisicao": str(uuid4())})
    assert canceled.status_code == 200
    still_available = client.get("/questionario-pre-triagem/ultima-resposta?hemocentro_id=1",
                                 headers=headers["doador"])
    assert still_available.json()["encontrado"] is True


def test_ultima_resposta_incompativel_nao_retorna_respostas_anteriores(agenda):
    client, _, headers, _ = agenda
    first = enviar(agenda, questionario_payload())
    assert first.status_code == 201
    slot = slots(agenda)[1]
    newer = questionario_payload()
    newer["versao"] = "pre-triagem-v2"
    with patch("app.services.questionario.VERSAO", "pre-triagem-v2"):
        response = client.post("/agendamentos", headers=headers["doador"], json={
            "horario_id": slot["id"], "chave_requisicao": str(uuid4()), "questionario": newer,
        })
    assert response.status_code == 201, response.text
    latest = client.get("/questionario-pre-triagem/ultima-resposta?hemocentro_id=1",
                        headers=headers["doador"])
    assert latest.status_code == 200
    assert latest.json()["encontrado"] is True
    assert latest.json()["compativel"] is False
    assert latest.json()["respostas"] == []


def test_questionario_ignora_antiga_flag_de_publicacao(agenda, monkeypatch):
    client, _, headers, _ = agenda
    monkeypatch.setenv("PRE_TRIAGEM_PUBLICADA", "false")
    assert client.get("/questionario-pre-triagem", headers=headers["doador"]).json()["publicado"] is True
    assert enviar(agenda, questionario_payload()).status_code == 201


@pytest.mark.parametrize("variavel", ["PRIVACIDADE_CONTROLADOR", "PRIVACIDADE_CANAL"])
def test_publicacao_exige_identificacao_institucional(agenda, monkeypatch, variavel):
    client, _, headers, _ = agenda
    monkeypatch.delenv(variavel)
    response = enviar(agenda, questionario_payload())
    assert response.status_code == 503
    assert client.get("/questionario-pre-triagem", headers=headers["doador"]).status_code == 503


def test_rejeita_contrato_livre_e_ausencia_de_formulario(agenda):
    client, engine, headers, _ = agenda
    slot = slots(agenda)[0]
    for extra in ({}, {"respostas_pre_triagem": []}, {
        "respostas_pre_triagem": [{"pergunta": "SEGREDO_TESTE", "resposta": "SEGREDO_TESTE"}],
    }):
        response = client.post("/agendamentos", headers=headers["doador"], json={
            "horario_id": slot["id"], "chave_requisicao": str(uuid4()), **extra,
        })
        assert response.status_code == 422
        assert "SEGREDO_TESTE" not in response.text
    with Session(engine) as db:
        assert db.scalar(select(Agendamento.id)) is None


@pytest.mark.parametrize("caso", [
    "faltante", "duplicada", "desconhecida", "enum", "oculta", "confirmacao",
    "confirmacao_duplicada", "peso_zero", "peso_infinito", "peso_limite", "peso_texto",
    "data_futura", "data_invalida", "multipla_exclusiva", "valor_duplicado",
    "lista_escolha", "valor_numero", "texto_grande", "campo_extra",
])
def test_rejeita_questionario_invalido_sem_gravar_reserva(agenda, caso):
    data = questionario_payload()
    if caso == "faltante":
        data["respostas"].pop(0)
    elif caso == "duplicada":
        data["respostas"].append(data["respostas"][0])
    elif caso == "desconhecida":
        alterar(data, "pergunta_inventada", ["nao"])
    elif caso == "enum":
        alterar(data, "sintomas", ["SEGREDO_TESTE"])
    elif caso == "oculta":
        alterar(data, "ultima_doacao", ["2000-01-01"])
    elif caso == "confirmacao":
        data["confirmacoes"].pop()
    elif caso == "confirmacao_duplicada":
        data["confirmacoes"] = ["veracidade"] * 3
    elif caso.startswith("peso_"):
        alterar(data, "peso", [{
            "peso_zero": "0", "peso_infinito": "NaN", "peso_limite": "1000", "peso_texto": "SEGREDO_TESTE",
        }[caso]])
    elif caso.startswith("data_"):
        alterar(data, "vacinas", ["sim"])
        alterar(data, "vacina_data", [
            (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
            if caso == "data_futura" else "2026-02-30",
        ])
    elif caso == "multipla_exclusiva":
        alterar(data, "procedimentos", ["nenhum", "cirurgia"])
    elif caso == "valor_duplicado":
        alterar(data, "procedimentos", ["nenhum", "nenhum"])
    elif caso == "lista_escolha":
        alterar(data, "sintomas", ["sim", "nao"])
    elif caso == "valor_numero":
        alterar(data, "peso", [70])
    elif caso == "texto_grande":
        alterar(data, "outras_informacoes", ["SEGREDO_TESTE" * 200])
    elif caso == "campo_extra":
        data["SEGREDO_TESTE"] = "SEGREDO_TESTE"
    response = enviar(agenda, data)
    assert response.status_code == 422, response.text
    assert "SEGREDO_TESTE" not in response.text
    assert response.headers["cache-control"] == "no-store"
    with Session(agenda[1]) as db:
        assert db.scalar(select(Agendamento.id)) is None
    assert slots(agenda)[0]["vagas_disponiveis"] == 1


@pytest.mark.parametrize("campo", ["versao", "versao_aviso"])
def test_versao_desatualizada_exige_revisao(agenda, campo):
    data = questionario_payload()
    data[campo] = "versao-inexistente"
    assert enviar(agenda, data).status_code == 409


def test_saude_nao_define_aptidao_e_snapshot_e_canonico(agenda):
    data = questionario_payload()
    for id in ("sintomas", "tratamento", "condicao_saude", "medicamentos", "exposicoes", "prep_pep"):
        alterar(data, id, ["sim"])
    alterar(data, "peso", ["40"])
    alterar(data, "prep_detalhe", ["MEDICAMENTO_CONFIDENCIAL_TESTE"])
    response = enviar(agenda, data)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "AGENDADO"
    with Session(agenda[1]) as db:
        record = db.get(Agendamento, response.json()["id"])
        assert record.questionario_pre_triagem["versao"] == data["versao"]
        instant = datetime.fromisoformat(record.questionario_pre_triagem["enviado_em"])
        assert instant.utcoffset() == timedelta(0)
        assert any(item["resposta"] == "MEDICAMENTO_CONFIDENCIAL_TESTE" for item in record.respostas_pre_triagem)
        assert record.respostas_pre_triagem[0]["pergunta"] == "Qual é seu peso atual, em kg?"
        logs = db.scalars(select(AuditLog)).all()
        assert all("MEDICAMENTO_CONFIDENCIAL_TESTE" not in str(item.metadata_json) for item in logs)


def test_condicionais_e_desconhecimento_explicito(agenda):
    data = questionario_payload()
    alterar(data, "peso", ["desconhecido"])
    alterar(data, "doacao_anterior", ["sim"])
    alterar(data, "ultima_doacao", ["desconhecido"])
    alterar(data, "reacao_anterior", ["reservado"])
    alterar(data, "vacinas", ["sim"])
    alterar(data, "vacina_data", ["desconhecido"])
    alterar(data, "procedimentos", ["cirurgia", "tatuagem"])
    alterar(data, "procedimento_data", ["desconhecido"])
    assert enviar(agenda, data).status_code == 201


def test_idempotencia_ordem_versao_e_publicacao(agenda, monkeypatch):
    client, engine, headers, _ = agenda
    data = questionario_payload()
    slot = slots(agenda)[0]
    body = {"horario_id": slot["id"], "chave_requisicao": str(uuid4()), "questionario": data}
    first = client.post("/agendamentos", headers=headers["doador"], json=body)
    assert first.status_code == 201
    data["respostas"].reverse()
    data["confirmacoes"].reverse()
    with patch("app.services.questionario.VERSAO", "pre-triagem-v2"):
        repeated = client.post("/agendamentos", headers=headers["doador"], json=body)
        assert repeated.status_code == 201
        assert repeated.json()["id"] == first.json()["id"]
    assert client.post("/agendamentos", headers=headers["doador"], json=body).status_code == 201
    alterar(data, "gestacao", ["nao"])
    assert client.post("/agendamentos", headers=headers["doador"], json=body).status_code == 409
    with Session(engine) as db:
        assert len(db.scalars(select(Agendamento)).all()) == 1


def test_detalhe_tem_escopo_e_auditoria_sem_conteudo(context):
    client, engine, headers, _ = context
    id = receber(context)
    response = client.get(f"/triagens/{id}", headers=headers["enfermeiro"])
    assert response.status_code == 200
    assert response.json()["questionario"]["versao"] == "pre-triagem-v1"
    assert "respostas" not in response.json()["questionario"]
    for perfil, status in (("externo", 404), ("recepcao", 403), ("admin", 403), ("outro_doador", 403)):
        assert client.get(f"/triagens/{id}", headers=headers[perfil]).status_code == status
    recepcao = client.get("/recepcao/agendamentos", headers=headers["recepcao"])
    assert "pre_triagem" not in recepcao.text and "questionario" not in recepcao.text
    with Session(engine) as db:
        eventos = db.scalars(select(AuditLog).where(AuditLog.event_type == "PRE_TRIAGEM_CONSULTADA")).all()
        assert len(eventos) == 1
        assert eventos[0].metadata_json == {"atendimento_id": id, "motivo": "atendimento"}


def test_legado_permanece_legivel_e_sem_aceite_inventado(context):
    client, engine, headers, _ = context
    id = receber(context)
    with Session(engine) as db:
        record = db.get(Agendamento, id)
        record.questionario_pre_triagem = None
        record.respostas_pre_triagem = [{"pergunta": "Pergunta antiga", "resposta": "Resposta antiga"}]
        db.commit()
    detalhe = client.get(f"/triagens/{id}", headers=headers["enfermeiro"]).json()
    assert detalhe["questionario"] is None
    assert detalhe["pre_triagem"] == [{"pergunta": "Pergunta antiga", "resposta": "Resposta antiga"}]
    export = client.get("/privacy/export", headers=headers["doador"]).json()
    assert export["titular"]["atendimentos"][0]["questionario"] is None


def test_canonico_independe_da_ordem_sem_modificar_entrada():
    data = QuestionarioSubmission.model_validate(questionario_payload())
    before = data.model_dump()
    canonical = canonico(data)
    assert data.model_dump() == before
    assert canonical["confirmacoes"] == sorted(data.confirmacoes)


def test_validacao_nao_depende_de_limite_clinico(context):
    data = QuestionarioSubmission.model_validate(alterar(questionario_payload(), "peso", ["999.9"]))
    assert validar(data)[0]["resposta"] == "999.9"
