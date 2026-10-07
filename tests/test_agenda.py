from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agendamento, AlteracaoAgendamento, HorarioAgenda, Usuario
from app.schemas.agenda import AgendaConfig
from app.security.audit import verificar_integridade
from app.security.session import utcnow
from app.services.agenda import _horarios_do_dia
from tests.test_triagens import context  # noqa: F401


def config_payload(versao=1, capacidade=1):
    return {
        "fuso_horario": "America/Sao_Paulo", "duracao_minutos": 30, "capacidade": capacidade,
        "antecedencia_minutos": 0, "horizonte_dias": 7, "cancelamento_minutos": 60,
        "remarcacao_minutos": 60, "publicada": True, "versao": versao, "excecoes": [],
        "periodos": [{"dia_semana": day, "inicio": "09:00", "fim": "11:00"} for day in range(7)],
    }


@pytest.fixture()
def agenda(context):
    client, _, headers, _ = context
    response = client.put("/hemocentros/1/agenda", headers=headers["admin"], json=config_payload())
    assert response.status_code == 200, response.text
    return context


def slots(context):
    client, _, headers, _ = context
    day = (utcnow() + timedelta(days=1)).date().isoformat()
    response = client.get(f"/hemocentros/1/disponibilidade?inicio={day}&fim={day}", headers=headers["doador"])
    assert response.status_code == 200, response.text
    return response.json()["dias"][0]["horarios"]


def book(context, slot_id, donor="doador", key=None):
    client, _, headers, _ = context
    return client.post("/agendamentos", headers=headers[donor], json={
        "horario_id": slot_id, "chave_requisicao": key or str(uuid4()),
        "respostas_pre_triagem": [],
    })


def change_body(reservation):
    return {"versao": reservation["versao"], "chave_requisicao": str(uuid4())}


def test_reserva_real_capacidade_e_idempotencia(agenda):
    slot = slots(agenda)[0]
    key = str(uuid4())
    first = book(agenda, slot["id"], key=key)
    assert first.status_code == 201, first.text
    repeated = book(agenda, slot["id"], key=key)
    assert repeated.status_code == 201 and repeated.json()["id"] == first.json()["id"]
    assert book(agenda, slot["id"], donor="outro_doador").status_code == 409
    assert slots(agenda)[0]["vagas_disponiveis"] == 0
    _, engine, _, _ = agenda
    with Session(engine) as db:
        assert len(db.scalars(select(Agendamento)).all()) == 1
        assert len(db.scalars(select(AlteracaoAgendamento)).all()) == 1
        assert verificar_integridade(db) == (True, None)


def test_chave_nao_pode_ser_reutilizada_com_outros_dados(agenda):
    available = slots(agenda)
    key = str(uuid4())
    assert book(agenda, available[0]["id"], key=key).status_code == 201
    assert book(agenda, available[1]["id"], key=key).status_code == 409


def test_cancelamento_libera_uma_vaga_sem_apagar_registro(agenda):
    client, engine, headers, _ = agenda
    slot = slots(agenda)[0]
    reservation = book(agenda, slot["id"]).json()
    data = change_body(reservation)
    path = f"/agendamentos/{reservation['id']}/cancelar"
    result = client.post(path, headers=headers["doador"], json=data)
    assert result.status_code == 200 and result.json()["status"] == "CANCELADO"
    assert client.post(path, headers=headers["doador"], json=data).status_code == 200
    assert slots(agenda)[0]["vagas_disponiveis"] == 1
    assert book(agenda, slot["id"], donor="outro_doador").status_code == 201
    assert client.get("/triagens", headers=headers["enfermeiro"]).json()["total"] == 0
    assert client.get("/recepcao/agendamentos", headers=headers["recepcao"]).json()["total"] == 1
    with Session(engine) as db:
        assert db.get(Agendamento, reservation["id"]).status == "CANCELADO"
        assert len(db.scalars(select(AlteracaoAgendamento).where(
            AlteracaoAgendamento.agendamento_id == reservation["id"],
        )).all()) == 2


def test_remarcacao_atomica_preserva_original_quando_destino_lota(agenda):
    client, _, headers, _ = agenda
    available = slots(agenda)
    original = book(agenda, available[0]["id"]).json()
    assert book(agenda, available[1]["id"], donor="outro_doador").status_code == 201
    data = {**change_body(original), "horario_id": available[1]["id"]}
    path = f"/agendamentos/{original['id']}/remarcar"
    assert client.post(path, headers=headers["doador"], json=data).status_code == 409
    unchanged = client.get("/agendamentos/me", headers=headers["doador"]).json()[0]
    assert unchanged["horario_id"] == original["horario_id"] and unchanged["versao"] == 1
    data["horario_id"] = available[2]["id"]
    changed = client.post(path, headers=headers["doador"], json=data)
    assert changed.status_code == 200, changed.text
    assert changed.json()["id"] == original["id"] and changed.json()["versao"] == 2
    assert client.post(path, headers=headers["doador"], json=data).status_code == 200
    occupancy = slots(agenda)
    assert occupancy[0]["vagas_disponiveis"] == 1 and occupancy[2]["vagas_disponiveis"] == 0
    assert changed.json()["alteracoes"][-1]["acao"] == "REMARCADO"


@pytest.mark.parametrize("acao", ["cancelar", "remarcar"])
def test_alteracoes_bloqueiam_outro_doador_e_atendimento_recebido(agenda, acao):
    client, _, headers, _ = agenda
    available = slots(agenda)
    reservation = book(agenda, available[0]["id"]).json()
    data = change_body(reservation)
    if acao == "remarcar":
        data["horario_id"] = available[1]["id"]
    path = f"/agendamentos/{reservation['id']}/{acao}"
    assert client.post(path, headers=headers["outro_doador"], json=data).status_code == 404
    assert client.post(f"/recepcao/agendamentos/{reservation['id']}/receber", headers=headers["recepcao"],
                       json={"versao": reservation["versao"]}).status_code == 200
    assert client.post(path, headers=headers["doador"], json=data).status_code == 409


def test_versao_desatualizada_nao_altera_reserva(agenda):
    client, _, headers, _ = agenda
    available = slots(agenda)
    original = book(agenda, available[0]["id"]).json()
    change = {**change_body(original), "horario_id": available[1]["id"]}
    assert client.post(f"/agendamentos/{original['id']}/remarcar", headers=headers["doador"], json=change).status_code == 200
    assert client.post(f"/agendamentos/{original['id']}/cancelar",
                       headers=headers["doador"], json=change_body(original)).status_code == 409


def test_recepcao_rejeita_versao_anterior_a_remarcacao(agenda):
    client, _, headers, _ = agenda
    available = slots(agenda)
    original = book(agenda, available[0]["id"]).json()
    moved = client.post(f"/agendamentos/{original['id']}/remarcar", headers=headers["doador"],
                        json={**change_body(original), "horario_id": available[1]["id"]}).json()
    path = f"/recepcao/agendamentos/{original['id']}/receber"
    response = client.post(path, headers=headers["recepcao"], json={"versao": original["versao"]})
    assert response.status_code == 409
    current = client.get("/agendamentos/me", headers=headers["doador"]).json()[0]
    assert current["status"] == "AGENDADO" and current["horario_id"] == available[1]["id"]
    assert client.post(path, headers=headers["recepcao"], json={"versao": moved["versao"]}).status_code == 200


def test_limite_exato_de_cancelamento(agenda):
    client, _, headers, _ = agenda
    reservation = book(agenda, slots(agenda)[0]["id"]).json()
    deadline = datetime.fromisoformat(reservation["cancelavel_ate"]).replace(tzinfo=None)
    with patch("app.services.agenda.utcnow", return_value=deadline):
        response = client.post(f"/agendamentos/{reservation['id']}/cancelar", headers=headers["doador"],
                               json=change_body(reservation))
        assert response.status_code == 409
        assert response.json()["detail"] == "O prazo para esta alteracao terminou."


def test_agenda_nao_pode_invalidar_reservas_e_politica_e_preservada(agenda):
    client, _, headers, _ = agenda
    reservation = book(agenda, slots(agenda)[0]["id"]).json()
    data = config_payload(versao=2)
    data["excecoes"] = [{"data": reservation["agendado_em"][:10], "periodos": []}]
    assert client.put("/hemocentros/1/agenda", headers=headers["admin"], json=data).status_code == 409
    data["excecoes"] = []
    data["cancelamento_minutos"] = 240
    assert client.put("/hemocentros/1/agenda", headers=headers["admin"], json=data).status_code == 200
    unchanged = client.get("/agendamentos/me", headers=headers["doador"]).json()[0]
    assert unchanged["cancelavel_ate"] == reservation["cancelavel_ate"]


def test_fechamento_excecao_e_agenda_nao_publicada(agenda):
    client, _, headers, _ = agenda
    day = (utcnow() + timedelta(days=1)).date().isoformat()
    data = config_payload(versao=2)
    data["excecoes"] = [{"data": day, "periodos": []}]
    assert client.put("/hemocentros/1/agenda", headers=headers["admin"], json=data).status_code == 200
    response = client.get(f"/hemocentros/1/disponibilidade?inicio={day}&fim={day}", headers=headers["doador"])
    assert response.json()["situacao"] == "SEM_VAGAS" and response.json()["dias"][0]["horarios"] == []
    data.update(versao=3, publicada=False)
    assert client.put("/hemocentros/1/agenda", headers=headers["admin"], json=data).status_code == 200
    assert client.get("/hemocentros/1/disponibilidade", headers=headers["doador"]).json()["situacao"] == "SEM_AGENDA"


@pytest.mark.parametrize("role", ["doador", "enfermeiro", "recepcao"])
def test_somente_gestores_configuram_agenda(agenda, role):
    client, _, headers, _ = agenda
    assert client.put("/hemocentros/1/agenda", headers=headers[role], json=config_payload(2)).status_code == 403


def test_responsavel_restrito_a_propria_unidade(agenda):
    client, engine, headers, ids = agenda
    with Session(engine) as db:
        db.get(Usuario, ids["recepcao"]).perfil = "RESPONSAVEL_HEMOCENTRO"
        db.commit()
    assert client.get("/hemocentros/1/agenda", headers=headers["recepcao"]).status_code == 200
    assert client.get("/hemocentros/2/agenda", headers=headers["recepcao"]).status_code == 403


@pytest.mark.parametrize("field,value", [
    ("fuso_horario", "Fuso/Inexistente"), ("capacidade", 0), ("duracao_minutos", 0),
    ("horizonte_dias", 181), ("periodos", [{"dia_semana": 0, "inicio": "11:00", "fim": "09:00"}]),
])
def test_configuracao_invalida(agenda, field, value):
    client, _, headers, _ = agenda
    data = config_payload(2)
    data[field] = value
    assert client.put("/hemocentros/1/agenda", headers=headers["admin"], json=data).status_code == 422


def test_conciliacao_legada_nao_promete_vaga_silenciosamente(agenda):
    client, engine, headers, ids = agenda
    day = (utcnow() + timedelta(days=1)).date()
    with Session(engine) as db:
        legacy = Agendamento(doador_id=ids["doador"], hemocentro_id=1,
                             agendado_em=datetime.combine(day, datetime.min.time()).replace(hour=12),
                             respostas_pre_triagem=[], criado_em=utcnow(), status="AGENDADO")
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id
    config = client.get("/hemocentros/1/agenda", headers=headers["admin"]).json()
    assert config["pendencias_legadas"][0]["id"] == legacy_id
    assert client.put("/hemocentros/1/agenda", headers=headers["admin"], json=config_payload(2)).status_code == 200
    reservation = client.get("/agendamentos/me", headers=headers["doador"]).json()[0]
    assert reservation["horario_id"] is not None and reservation["alteracoes"][0]["acao"] == "CONCILIADO"
    assert slots(agenda)[0]["vagas_disponiveis"] == 0


def test_exclusao_de_conta_libera_reserva_sem_excluir_historico(agenda):
    client, engine, headers, _ = agenda
    slot = slots(agenda)[0]
    reservation = book(agenda, slot["id"]).json()
    assert client.delete("/privacy/me", headers=headers["doador"]).status_code == 200
    with Session(engine) as db:
        assert db.get(Agendamento, reservation["id"]).status == "CANCELADO"
    assert book(agenda, slot["id"], donor="outro_doador").status_code == 201


def test_horarios_ambiguos_sao_explicitos_e_nao_ofertados():
    data = config_payload()
    data.update(fuso_horario="America/New_York",
                periodos=[{"dia_semana": 6, "inicio": "01:00", "fim": "03:00"}])
    horarios, warnings = _horarios_do_dia(AgendaConfig.model_validate(data), datetime(2026, 11, 1).date())
    assert warnings and len(horarios) == 2


def test_cancelamento_e_remarcacao_constam_na_exportacao_privacidade(agenda):
    client, _, headers, _ = agenda
    available = slots(agenda)
    original = book(agenda, available[0]["id"]).json()
    response = client.post(f"/agendamentos/{original['id']}/remarcar", headers=headers["doador"],
                           json={**change_body(original), "horario_id": available[1]["id"]})
    assert response.status_code == 200
    assert client.post(f"/agendamentos/{original['id']}/cancelar", headers=headers["doador"],
                       json=change_body(response.json())).status_code == 200
    export = client.get("/privacy/export", headers=headers["doador"])
    assert export.status_code == 200
    atendimento = export.json()["titular"]["atendimentos"][0]
    assert atendimento["status"] == "CANCELADO"
    assert [item["acao"] for item in atendimento["alteracoes"]] == ["RESERVADO", "REMARCADO", "CANCELADO"]
    assert atendimento["alteracoes"][1]["agendado_anterior"] == original["agendado_em"]


def test_horizonte_e_intervalo_de_consulta_sao_verificados(agenda):
    client, _, headers, _ = agenda
    day = (utcnow() + timedelta(days=8)).date().isoformat()
    result = client.get(f"/hemocentros/1/disponibilidade?inicio={day}&fim={day}", headers=headers["doador"])
    assert result.status_code == 200 and result.json()["dias"][0]["horarios"] == []
    today = utcnow().date().isoformat()
    end = (utcnow() + timedelta(days=31)).date().isoformat()
    assert client.get(f"/hemocentros/1/disponibilidade?inicio={today}&fim={end}", headers=headers["doador"]).status_code == 422


def test_antecedencia_minima_no_limite_exato(agenda):
    client, _, headers, _ = agenda
    data = config_payload(2)
    data["antecedencia_minutos"] = 60
    assert client.put("/hemocentros/1/agenda", headers=headers["admin"], json=data).status_code == 200
    slot = slots(agenda)[0]
    start = datetime.fromisoformat(slot["inicio"]).replace(tzinfo=None)
    with patch("app.services.agenda.utcnow", return_value=start - timedelta(minutes=60)):
        assert book(agenda, slot["id"]).status_code == 201
    with patch("app.services.agenda.utcnow", return_value=start - timedelta(minutes=60) + timedelta(microseconds=1)):
        response = book(agenda, slot["id"], donor="outro_doador")
        assert response.status_code == 409
        assert response.json()["detail"] == "Horario fora do prazo permitido. Atualize a disponibilidade."


def test_remarcacao_nao_troca_hemocentro(agenda):
    client, _, headers, _ = agenda
    original = book(agenda, slots(agenda)[0]["id"]).json()
    day = (utcnow() + timedelta(days=1)).date().isoformat()
    other = client.get(f"/hemocentros/2/disponibilidade?inicio={day}&fim={day}", headers=headers["doador"]).json()["dias"][0]["horarios"][0]
    response = client.post(f"/agendamentos/{original['id']}/remarcar", headers=headers["doador"],
                           json={**change_body(original), "horario_id": other["id"]})
    assert response.status_code == 404
    assert client.get("/agendamentos/me", headers=headers["doador"]).json()[0]["hemocentro_id"] == 1


def test_exclusao_de_unidade_configurada_sem_reservas_limpa_agenda(agenda):
    client, engine, headers, _ = agenda
    assert slots(agenda)
    assert client.delete("/hemocentros/1", headers=headers["admin"]).status_code == 204
    with Session(engine) as db:
        assert db.scalars(select(HorarioAgenda).where(HorarioAgenda.hemocentro_id == 1)).all() == []


def test_exclusao_de_unidade_com_reservas_preserva_historico(agenda):
    client, _, headers, _ = agenda
    reservation = book(agenda, slots(agenda)[0]["id"]).json()
    assert client.delete("/hemocentros/1", headers=headers["admin"]).status_code == 409
    assert client.get("/agendamentos/me", headers=headers["doador"]).json()[0]["id"] == reservation["id"]
