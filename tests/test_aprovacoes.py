import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, AuthSession, Hemocentro, Usuario
from app.models.password_reset_token import PasswordResetToken
from app.models.two_factor_code import TwoFactorCode
from app.schemas.usuario import AprovarEnfermeiroRequest
from app.security.audit import verificar_integridade
from app.security.password import hash_password
from app.security.session import issue_session, utcnow
from app.security.two_factor import hash_code
from app.services.aprovacoes import aprovar_enfermeiro
from tests.test_triagens import context  # noqa: F401


def payload(**overrides):
    data = {
        "nome": "Enfermeira solicitante", "cpf": "12345678901",
        "email": "solicitante@example.com", "senha": "SenhaSegura123!",
        "perfil": "ENFERMEIRO", "status": "INATIVO", "hemocentro_id": None,
        "coren_numero": "765432", "coren_uf": "SP",
        "consentimento_aceito": True, "consentimento_versao": "v1.1",
        "consentimento_finalidades": ["cadastro", "autenticacao", "triagem"],
    }
    data.update(overrides)
    return data


def solicitar(context, **overrides):
    response = context[0].post("/usuarios/solicitar-enfermagem", json=payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def aprovar(context, usuario_id, **overrides):
    data = {"hemocentro_id": 1, "conferencia_confirmada": True}
    data.update(overrides)
    return context[0].post(f"/usuarios/aprovacoes/{usuario_id}/aprovar",
                           headers=context[2]["admin"], json=data)


def test_cadastro_publico_pendente_e_doador_preservado(context):
    client, engine, headers, _ = context
    # Uma sessão administrativa no navegador não pode liberar o cadastro público.
    response = client.post("/usuarios/solicitar-enfermagem", headers=headers["admin"],
                           json=payload(coren_numero=" 765432 ", coren_uf=" sp "))
    assert response.status_code == 201, response.text
    nurse = response.json()
    assert nurse["perfil"] == "ENFERMEIRO" and nurse["status"] == "INATIVO"
    assert nurse["aprovacao_pendente"] is True and nurse["hemocentro_id"] is None
    assert nurse["coren_numero"] == "765432" and nurse["coren_uf"] == "SP"
    assert "senha" not in nurse and "senha_hash" not in nurse
    donor = client.post("/usuarios", json=payload(
        nome="Doador", cpf="12345678902", email="novo-doador@example.com",
        perfil="DOADOR", status="ATIVO", coren_numero=None, coren_uf=None,
    ))
    assert donor.status_code == 201, donor.text
    assert donor.json()["status"] == "ATIVO" and donor.json()["aprovacao_pendente"] is False
    with Session(engine) as db:
        event = db.scalar(select(AuditLog).where(AuditLog.event_type == "ENFERMEIRO_CADASTRO_PENDENTE"))
        assert event.metadata_json == {"alvo_usuario_id": nurse["id"]}
        assert "765432" not in str(event.metadata_json)


@pytest.mark.parametrize("changes", [
    {"coren_numero": None}, {"coren_numero": ""}, {"coren_numero": "12A"},
    {"coren_numero": "123-SP"}, {"coren_numero": "1" * 21},
    {"coren_numero": "١٢٣"}, {"coren_uf": None}, {"coren_uf": "XX"},
    {"status": "ATIVO"}, {"perfil": "ADMINISTRADOR"}, {"perfil": "DOADOR"},
    {"hemocentro_id": 1}, {"aprovacao_pendente": False},
    {"aprovado_por": 1}, {"aprovado_em": "2026-01-01"},
    {"consentimento_aceito": False},
])
def test_cadastro_invalido_ou_autoaprovacao_rejeitado(context, changes):
    client, engine, _, _ = context
    response = client.post("/usuarios/solicitar-enfermagem", json=payload(**changes))
    assert response.status_code == 422, response.text
    with Session(engine) as db:
        assert db.scalar(select(Usuario).where(Usuario.email == "solicitante@example.com")) is None


def test_credencial_exclusiva_e_unicidade_por_uf(context):
    client = context[0]
    solicitar(context)
    duplicate = client.post("/usuarios/solicitar-enfermagem", json=payload(
        cpf="12345678902", email="duplicado@example.com", coren_uf=" sp ",
    ))
    assert duplicate.status_code == 409 and "COREN" in duplicate.json()["detail"]
    assert solicitar(context, cpf="12345678902", email="outro-estado@example.com",
                     coren_uf="RJ")["coren_uf"] == "RJ"
    donor = client.post("/usuarios", json=payload(
        perfil="DOADOR", status="ATIVO", cpf="12345678903", email="doador3@example.com",
    ))
    assert donor.status_code == 422
    nurse = client.post("/usuarios", json=payload(status="ATIVO", hemocentro_id=1,
                                                cpf="12345678904", email="nurse4@example.com"))
    assert nurse.status_code == 401


@pytest.mark.parametrize("status", ["INATIVO", "ATIVO"])
def test_pendente_sem_login_2fa_sessao_ou_reset(context, status):
    client, engine, _, _ = context
    created = solicitar(context)
    now = utcnow()
    token = "synthetic-pending-session"
    reset = "synthetic-pending-reset"
    with Session(engine) as db:
        nurse = db.get(Usuario, created["id"])
        nurse.status = status
        db.add_all([
            AuthSession(usuario_id=nurse.id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                        created_at=now, last_activity_at=now),
            TwoFactorCode(usuario_id=nurse.id, code_hash=hash_code("123456"),
                          created_at=now, expires_at=now + timedelta(minutes=5)),
            PasswordResetToken(usuario_id=nurse.id, token_hash=hashlib.sha256(reset.encode()).hexdigest(),
                               created_at=now, expires_at=now + timedelta(minutes=15)),
        ])
        db.commit()
        with pytest.raises(HTTPException) as rejected:
            issue_session(db, nurse)
        assert rejected.value.status_code == 401
    with patch("app.services.auth.send_two_factor_code") as send_2fa, \
         patch("app.services.auth.send_password_reset_email") as send_reset:
        login = client.post("/auth/login", json={"email": created["email"], "senha": "SenhaSegura123!"})
        assert login.status_code == 401
        assert login.json()["detail"] == "E-mail ou senha inválidos."
        assert client.post("/auth/2fa/verify", json={"email": created["email"], "code": "123456"}).status_code == 401
        assert client.post("/auth/forgot-password", json={"email": created["email"]}).status_code == 200
        assert client.post("/auth/reset-password", json={"token": reset, "senha": "NovaSenhaSegura123!"}).status_code == 400
        send_2fa.assert_not_called(); send_reset.assert_not_called()
    for path in ["/auth/me", "/triagens", "/usuarios/aprovacoes/pendentes"]:
        assert client.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 401


@pytest.mark.parametrize("role", [None, "doador", "enfermeiro", "recepcao", "medico"])
def test_aprovacao_apenas_admin(context, role):
    client, _, headers, _ = context
    nurse = solicitar(context)
    auth = headers[role] if role else {}
    expected = 403 if role else 401
    assert client.get("/usuarios/aprovacoes/pendentes", headers=auth).status_code == expected
    assert client.post(f"/usuarios/aprovacoes/{nurse['id']}/aprovar", headers=auth,
                       json={"hemocentro_id": 1, "conferencia_confirmada": True}).status_code == expected


@pytest.mark.parametrize("changes", [
    {"conferencia_confirmada": False}, {"conferencia_confirmada": None},
    {"conferencia_confirmada": 1}, {"conferencia_confirmada": "true"},
    {"hemocentro_id": 0}, {"hemocentro_id": 999}, {"status": "ATIVO"},
])
def test_aprovacao_exige_conferencia_e_unidade_valida(context, changes):
    nurse = solicitar(context)
    assert aprovar(context, nurse["id"], **changes).status_code == 422
    with Session(context[1]) as db:
        assert db.get(Usuario, nurse["id"]).aprovacao_pendente is True


def test_sem_conferencia_ou_unidade_inativa(context):
    client, engine, headers, _ = context
    nurse = solicitar(context)
    assert client.post(f"/usuarios/aprovacoes/{nurse['id']}/aprovar", headers=headers["admin"],
                       json={"hemocentro_id": 1}).status_code == 422
    with Session(engine) as db:
        db.get(Hemocentro, 1).status = "INATIVO"
        db.commit()
    assert aprovar(context, nurse["id"]).status_code == 422
    assert aprovar(context, 999).status_code == 404


def test_paginacao_e_put_nao_libera_pendente(context):
    client, _, headers, _ = context
    first = solicitar(context)
    second = solicitar(context, cpf="12345678902", email="segunda@example.com", coren_numero="765433")
    page = client.get("/usuarios/aprovacoes/pendentes?pagina=2&tamanho=1", headers=headers["admin"])
    assert page.status_code == 200
    assert page.json() == {"itens": [{"id": second["id"], "nome": second["nome"],
                                    "email": second["email"], "coren_numero": "765433", "coren_uf": "SP"}],
                           "total": 2, "pagina": 2, "tamanho": 1}
    for query in ["pagina=0", "tamanho=101"]:
        assert client.get(f"/usuarios/aprovacoes/pendentes?{query}", headers=headers["admin"]).status_code == 422
    body = {key: value for key, value in payload().items() if not key.startswith("consentimento")}
    for changes in [{"status": "ATIVO"}, {"perfil": "DOADOR"}, {"hemocentro_id": 1}]:
        response = client.put(f"/usuarios/{first['id']}", headers=headers["admin"], json={**body, **changes})
        assert response.status_code == 409


def test_aprovar_audita_libera_login_e_preserva_legados(context):
    client, engine, headers, ids = context
    nurse = solicitar(context)
    response = aprovar(context, nurse["id"], hemocentro_id=2)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ATIVO" and response.json()["hemocentro_id"] == 2
    assert response.json()["aprovacao_pendente"] is False
    assert client.get("/usuarios/aprovacoes/pendentes", headers=headers["admin"]).json()["total"] == 0
    assert aprovar(context, nurse["id"]).status_code == 409
    assert aprovar(context, ids["doador"]).status_code == 409
    with Session(engine) as db:
        user = db.get(Usuario, nurse["id"])
        assert user.aprovado_por == ids["admin"] and user.aprovado_em is not None
        legacy = db.get(Usuario, ids["enfermeiro"])
        assert legacy.status == "ATIVO" and not legacy.aprovacao_pendente and legacy.coren_numero is None
        event = db.scalar(select(AuditLog).where(AuditLog.event_type == "ENFERMEIRO_APROVADO"))
        assert event.user_id == ids["admin"]
        assert event.metadata_json == {"alvo_usuario_id": nurse["id"]}
        assert "765432" not in str(event.metadata_json)
        assert verificar_integridade(db) == (True, None)
    with patch("app.services.auth.send_two_factor_code") as mail:
        login = client.post("/auth/login", json={"email": nurse["email"], "senha": "SenhaSegura123!"})
        assert login.status_code == 200 and login.json()["requires_2fa"]
        code = mail.call_args.args[1]
    verified = client.post("/auth/2fa/verify", json={"email": nurse["email"], "code": code})
    assert verified.status_code == 200, verified.text
    assert verified.json()["usuario"]["perfil"] == "ENFERMEIRO"
    assert verified.json()["usuario"]["hemocentro_id"] == 2
    nurse_headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}
    assert client.get("/triagens", headers=nurse_headers).status_code == 200
    privacy = client.get("/privacy/me", headers=nurse_headers).json()
    assert privacy["coren_numero"] == "765432" and privacy["coren_uf"] == "SP"
    assert client.get("/privacy/export", headers=nurse_headers).json()["titular"]["coren_numero"] == "765432"
    assert client.delete("/privacy/me", headers=nurse_headers).status_code == 200
    with Session(engine) as db:
        user = db.get(Usuario, nurse["id"])
        assert user.coren_numero is None and user.coren_uf is None
        assert user.aprovado_por is None and user.aprovado_em is None
        assert user.aprovacao_pendente is False
    solicitar(context, cpf="12345678903", email="nova-inscricao@example.com")


def test_aprovacao_simultanea_apenas_um_sucesso(context):
    nurse = solicitar(context)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: aprovar(context, nurse["id"]), range(2)))
    assert sorted(response.status_code for response in results) == [200, 409]
    with Session(context[1]) as db:
        events = db.scalars(select(AuditLog).where(AuditLog.event_type == "ENFERMEIRO_APROVADO")).all()
        assert len(events) == 1
        assert verificar_integridade(db) == (True, None)


def test_estado_desatualizado_nao_reaprova(context):
    nurse = solicitar(context)
    with Session(context[1]) as stale:
        cached = stale.get(Usuario, nurse["id"])
        admin = stale.get(Usuario, context[3]["admin"])
        assert aprovar(context, nurse["id"]).status_code == 200
        assert cached.aprovacao_pendente is True
        with pytest.raises(HTTPException) as rejected:
            aprovar_enfermeiro(stale, admin, nurse["id"],
                              AprovarEnfermeiroRequest(hemocentro_id=2, conferencia_confirmada=True))
        assert rejected.value.status_code == 409
    with Session(context[1]) as db:
        assert db.get(Usuario, nurse["id"]).hemocentro_id == 1


def test_cadastro_simultaneo_mesmo_coren_retorna_conflito(context):
    barrier = Barrier(2)

    def synchronized_hash(senha):
        barrier.wait(timeout=10)
        return hash_password(senha)

    def enviar(index):
        return context[0].post("/usuarios/solicitar-enfermagem", json=payload(
            cpf=f"1234567890{index}", email=f"concorrente{index}@example.com",
        ))

    with patch("app.services.usuario.hash_password", side_effect=synchronized_hash):
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(enviar, [1, 2]))
    assert sorted(response.status_code for response in responses) == [201, 409]
    rejected = next(response for response in responses if response.status_code == 409)
    assert "COREN" in rejected.json()["detail"]
    with Session(context[1]) as db:
        nurses = db.scalars(select(Usuario).where(Usuario.coren_numero == "765432")).all()
        assert len(nurses) == 1 and nurses[0].aprovacao_pendente
        assert verificar_integridade(db) == (True, None)


@pytest.mark.parametrize("fase", ["cadastro", "aprovacao"])
def test_falha_de_auditoria_nao_persiste_alteracao_parcial(context, fase):
    created = solicitar(context) if fase == "aprovacao" else None
    module = "aprovacoes" if created else "usuario"
    with patch(f"app.services.{module}.registrar_evento", side_effect=RuntimeError("Synthetic audit failure")):
        with pytest.raises(RuntimeError, match="Synthetic audit failure"):
            if created:
                aprovar(context, created["id"])
            else:
                context[0].post("/usuarios/solicitar-enfermagem", json=payload())
    with Session(context[1]) as db:
        nurse = db.scalar(select(Usuario).where(Usuario.email == "solicitante@example.com"))
        if created:
            assert nurse.status == "INATIVO" and nurse.aprovacao_pendente is True
            assert nurse.hemocentro_id is None and nurse.aprovado_por is None
            assert nurse.aprovado_em is None
        else:
            assert nurse is None
        assert db.scalar(select(AuditLog).where(AuditLog.event_type == "ENFERMEIRO_APROVADO")) is None
