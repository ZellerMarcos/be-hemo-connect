from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models.hemocentro import Hemocentro
from app.models.triagem import Agendamento, Triagem
from app.models.usuario import Usuario
from app.schemas.triagem import (
    AgendamentoCreate, AvaliacaoUpdate, FilaItem, FilaResponse,
    HistoricoItem, IndicadoresResponse, TriagemDetalhe, TriagemFinalizar,
)
from app.security.audit import registrar_evento
from app.security.authorization import require_hemocentro
from app.security.session import utcnow


FINAL_STATUSES = ("APTO", "INAPTO", "ENCAMINHADO_MEDICO")


def get_scoped_agendamento(db: Session, usuario: Usuario, agendamento_id: int) -> Agendamento:
    query = select(Agendamento).where(Agendamento.id == agendamento_id)
    if usuario.perfil == "DOADOR":
        query = query.where(Agendamento.doador_id == usuario.id)
    elif usuario.perfil != "ADMINISTRADOR":
        query = query.where(Agendamento.hemocentro_id == require_hemocentro(usuario))
    agendamento = db.scalar(query)
    if agendamento is None:
        raise HTTPException(404, "Atendimento não encontrado.")
    return agendamento


def create_agendamento(db: Session, usuario: Usuario, data: AgendamentoCreate) -> Agendamento:
    centro = db.get(Hemocentro, data.hemocentro_id)
    if centro is None or centro.status != "ATIVO":
        raise HTTPException(422, "Hemocentro indisponível.")
    if data.agendado_em <= utcnow():
        raise HTTPException(422, "O agendamento deve ser para uma data futura.")
    agendamento = Agendamento(
        doador_id=usuario.id,
        hemocentro_id=data.hemocentro_id,
        agendado_em=data.agendado_em,
        respostas_pre_triagem=[resposta.model_dump() for resposta in data.respostas_pre_triagem],
        criado_em=utcnow(),
        status="AGENDADO",
    )
    db.add(agendamento)
    db.flush()
    registrar_evento(db, "AGENDAMENTO_CRIADO", "sucesso", user_id=usuario.id, atendimento_id=agendamento.id)
    db.refresh(agendamento)
    return agendamento


def query_fila(usuario: Usuario, *, status: str | None = None, busca: str | None = None,
               inicio: date | None = None, fim: date | None = None, recepcao: bool = False):
    query = select(Agendamento, Usuario, Triagem).join(
        Usuario, Usuario.id == Agendamento.doador_id
    ).outerjoin(Triagem, Triagem.agendamento_id == Agendamento.id)
    if usuario.perfil != "ADMINISTRADOR":
        query = query.where(Agendamento.hemocentro_id == require_hemocentro(usuario))
    query = query.where(Usuario.status == "ATIVO")
    if not recepcao:
        query = query.where(Agendamento.status != "AGENDADO")
    if status:
        query = query.where(Agendamento.status == status)
    if busca:
        digits = "".join(char for char in busca if char.isdigit())
        escaped = busca.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        condition = Usuario.nome.ilike(f"%{escaped}%", escape="\\")
        if digits:
            condition = or_(condition, Usuario.cpf.contains(digits))
        query = query.where(condition)
    if inicio:
        query = query.where(Agendamento.agendado_em >= datetime.combine(inicio, time.min))
    if fim:
        query = query.where(Agendamento.agendado_em < datetime.combine(fim + timedelta(days=1), time.min))
    return query


def list_fila(db: Session, usuario: Usuario, pagina: int, tamanho: int, **filters) -> FilaResponse:
    if filters.get("inicio") and filters.get("fim") and filters["inicio"] > filters["fim"]:
        raise HTTPException(422, "O início do período deve ser anterior ao fim.")
    query = query_fila(usuario, **filters)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(Agendamento.agendado_em, Agendamento.id)
                      .offset((pagina - 1) * tamanho).limit(tamanho)).all()
    itens = [FilaItem(
        **{key: getattr(agenda, key) for key in ("id", "hemocentro_id", "agendado_em", "status", "recebido_em")},
        nome=doador.nome,
        cpf_mascarado=f"***.***.{doador.cpf[6:9]}-{doador.cpf[9:]}",
        tipo_sanguineo=doador.tipo_sanguineo,
        enfermeiro_id=triagem.enfermeiro_id if triagem else None,
    ) for agenda, doador, triagem in rows]
    return FilaResponse(itens=itens, total=total, pagina=pagina, tamanho=tamanho)


def indicadores(db: Session, usuario: Usuario) -> IndicadoresResponse:
    rows = db.execute(select(Agendamento.status, func.count()).join(
        Usuario, Usuario.id == Agendamento.doador_id
    ).where(
        Agendamento.hemocentro_id == require_hemocentro(usuario), Usuario.status == "ATIVO"
    ).group_by(Agendamento.status)).all()
    counts = dict(rows)
    return IndicadoresResponse(
        pendentes=counts.get("AGUARDANDO_TRIAGEM", 0),
        em_atendimento=counts.get("EM_TRIAGEM", 0),
        concluidas=sum(counts.get(value, 0) for value in FINAL_STATUSES),
        encaminhadas_medico=counts.get("ENCAMINHADO_MEDICO", 0),
    )


def historico(db: Session, usuario: Usuario, doador_id: int) -> list[HistoricoItem]:
    query = select(Agendamento, Triagem).join(
        Triagem, Triagem.agendamento_id == Agendamento.id
    ).where(Agendamento.doador_id == doador_id, Triagem.finalizada_em.is_not(None))
    if usuario.perfil != "DOADOR":
        query = query.where(Agendamento.hemocentro_id == require_hemocentro(usuario))
    return [HistoricoItem(agendamento_id=agenda.id, data=avaliacao.finalizada_em,
                         resultado=avaliacao.resultado)
            for agenda, avaliacao in db.execute(query.order_by(Triagem.finalizada_em.desc())).all()]


def detalhe(db: Session, usuario: Usuario, agendamento_id: int) -> TriagemDetalhe:
    agenda = get_scoped_agendamento(db, usuario, agendamento_id)
    if agenda.status == "AGENDADO":
        raise HTTPException(409, "O atendimento ainda não foi recebido.")
    doador = db.get(Usuario, agenda.doador_id)
    if doador is None or doador.status != "ATIVO":
        raise HTTPException(404, "Atendimento não encontrado.")
    avaliacao = db.scalar(select(Triagem).where(Triagem.agendamento_id == agenda.id))
    return TriagemDetalhe(
        agendamento=agenda,
        doador=doador,
        pre_triagem=agenda.respostas_pre_triagem,
        historico=historico(db, usuario, agenda.doador_id),
        avaliacao=avaliacao,
    )


def receber(db: Session, usuario: Usuario, agendamento_id: int) -> Agendamento:
    agenda = get_scoped_agendamento(db, usuario, agendamento_id)
    doador = db.get(Usuario, agenda.doador_id)
    if doador is None or doador.status != "ATIVO":
        raise HTTPException(409, "Doador indisponível para atendimento.")
    changed = db.execute(update(Agendamento).where(
        Agendamento.id == agenda.id, Agendamento.status == "AGENDADO"
    ).values(status="AGUARDANDO_TRIAGEM", recebido_em=utcnow(), recebido_por=usuario.id))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "A chegada já foi confirmada ou o atendimento mudou.")
    registrar_evento(db, "DOADOR_RECEBIDO", "sucesso", user_id=usuario.id, atendimento_id=agenda.id)
    db.refresh(agenda)
    return agenda


def iniciar(db: Session, usuario: Usuario, agendamento_id: int) -> TriagemDetalhe:
    agenda = get_scoped_agendamento(db, usuario, agendamento_id)
    doador = db.get(Usuario, agenda.doador_id)
    if doador is None or doador.status != "ATIVO":
        raise HTTPException(409, "Doador indisponível para atendimento.")
    # A transição condicional e a avaliação pertencem à mesma transação.
    changed = db.execute(update(Agendamento).where(
        Agendamento.id == agenda.id, Agendamento.status == "AGUARDANDO_TRIAGEM"
    ).values(status="EM_TRIAGEM"))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Triagem já iniciada ou indisponível. Atualize a lista.")
    db.add(Triagem(agendamento_id=agenda.id, enfermeiro_id=usuario.id, iniciada_em=utcnow()))
    registrar_evento(db, "TRIAGEM_INICIADA", "sucesso", user_id=usuario.id, atendimento_id=agenda.id)
    return detalhe(db, usuario, agenda.id)


def salvar_avaliacao(db: Session, usuario: Usuario, agendamento_id: int,
                    data: AvaliacaoUpdate, finalizar: bool = False) -> TriagemDetalhe:
    agenda = get_scoped_agendamento(db, usuario, agendamento_id)
    avaliacao = db.scalar(select(Triagem).where(Triagem.agendamento_id == agenda.id))
    doador = db.get(Usuario, agenda.doador_id)
    if doador is None or doador.status != "ATIVO":
        raise HTTPException(409, "Doador indisponível para atendimento.")
    if avaliacao is None or agenda.status != "EM_TRIAGEM":
        raise HTTPException(409, "Triagem não está em atendimento.")
    if avaliacao.enfermeiro_id != usuario.id:
        raise HTTPException(403, "Somente o enfermeiro responsável pode registrar esta avaliação.")
    values = {"observacoes": data.observacoes, "versao": data.versao + 1}
    if finalizar:
        if not isinstance(data, TriagemFinalizar):
            raise HTTPException(422, "Resultado obrigatório.")
        values.update(resultado=data.resultado, finalizada_em=utcnow())
    changed = db.execute(update(Triagem).where(
        Triagem.id == avaliacao.id,
        Triagem.versao == data.versao,
        Triagem.finalizada_em.is_(None),
    ).values(**values))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "A avaliação mudou. Recarregue antes de continuar.")
    if finalizar:
        agenda.status = data.resultado
    action = "TRIAGEM_FINALIZADA" if finalizar else "TRIAGEM_AVALIACAO_SALVA"
    if finalizar and data.resultado == "ENCAMINHADO_MEDICO":
        action = "TRIAGEM_ENCAMINHADA_MEDICO"
    registrar_evento(db, action, "sucesso", user_id=usuario.id, atendimento_id=agenda.id)
    return detalhe(db, usuario, agenda.id)
