from collections import Counter
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.agenda import AgendaHemocentro, AlteracaoAgendamento, HorarioAgenda
from app.models.hemocentro import Hemocentro
from app.models.triagem import Agendamento
from app.models.usuario import Usuario
from app.schemas.agenda import (
    AgendaConfig, AgendaResponse, AlteracaoRequest, DiaDisponibilidade,
    DisponibilidadeResponse, HorarioResponse, RemarcacaoRequest, ReservaResponse,
)
from app.schemas.triagem import AgendamentoCreate, AgendamentoResponse
from app.security.audit import registrar_evento
from app.security.session import utcnow


def _centro(db: Session, centro_id: int) -> Hemocentro:
    # Uma mesma unidade serializa configuracao, reserva, cancelamento e remarcacao.
    centro = db.scalar(select(Hemocentro).where(Hemocentro.id == centro_id)
                       .with_for_update().execution_options(populate_existing=True))
    if centro is None:
        raise HTTPException(404, "Hemocentro nao encontrado.")
    return centro


def _doador(db: Session, usuario: Usuario) -> None:
    atual = db.scalar(select(Usuario).where(Usuario.id == usuario.id)
                      .with_for_update().execution_options(populate_existing=True))
    if atual is None or atual.status != "ATIVO" or atual.aprovacao_pendente:
        raise HTTPException(401, "Sessao invalida.")
    if atual.perfil != "DOADOR":
        raise HTTPException(403, "Somente doadores podem administrar suas reservas.")


def _gestor(db: Session, usuario: Usuario, centro_id: int) -> None:
    atual = db.scalar(select(Usuario).where(Usuario.id == usuario.id)
                      .with_for_update().execution_options(populate_existing=True))
    if atual is None or atual.status != "ATIVO" or atual.aprovacao_pendente:
        raise HTTPException(401, "Sessao invalida.")
    if atual.perfil != "ADMINISTRADOR" and not (
        atual.perfil == "RESPONSAVEL_HEMOCENTRO" and atual.hemocentro_id == centro_id
    ):
        raise HTTPException(403, "Sem permissao para administrar a agenda desta unidade.")


def _config(db: Session, centro_id: int) -> AgendaConfig | None:
    agenda = db.get(AgendaHemocentro, centro_id)
    return AgendaConfig.model_validate(agenda) if agenda else None


def consultar_agenda(db: Session, usuario: Usuario, centro_id: int) -> AgendaResponse:
    _centro(db, centro_id)
    _gestor(db, usuario, centro_id)
    config = _config(db, centro_id)
    pendentes = db.scalars(select(Agendamento).where(
        Agendamento.hemocentro_id == centro_id, Agendamento.horario_id.is_(None),
        Agendamento.status == "AGENDADO", Agendamento.agendado_em > utcnow(),
    ).order_by(Agendamento.agendado_em)).all()
    return AgendaResponse(
        configurada=config is not None, configuracao=config,
        pendencias_legadas=[{"id": row.id, "agendado_em": row.agendado_em} for row in pendentes],
    )


def _horarios_do_dia(config: AgendaConfig, day: date) -> tuple[list[tuple[datetime, datetime]], list[str]]:
    periods = [p for p in config.periodos if p.dia_semana == day.weekday()]
    exception = next((item for item in config.excecoes if item.data == day), None)
    if exception is not None:
        periods = exception.periodos
    zone = ZoneInfo(config.fuso_horario)
    duration = timedelta(minutes=config.duracao_minutos)
    result = []
    warnings = []
    for period in sorted(periods, key=lambda item: item.inicio):
        local = datetime.combine(day, period.inicio)
        end = datetime.combine(day, period.fim)
        while local + duration <= end:
            finish = local + duration
            bounds = []
            for value in (local, finish):
                aware = value.replace(tzinfo=zone)
                if (aware.utcoffset() != value.replace(tzinfo=zone, fold=1).utcoffset()
                        or aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != value):
                    break
                bounds.append(aware.astimezone(timezone.utc).replace(tzinfo=None))
            if len(bounds) == 2 and bounds[1] - bounds[0] == duration:
                result.append((bounds[0], bounds[1]))
            else:
                warnings.append(f"{day.isoformat()} {local:%H:%M}: horario nao ofertado por transicao de fuso.")
            local = finish
    return result, warnings


def _materializar(db: Session, centro_id: int, config: AgendaConfig, day: date) -> tuple[list[HorarioAgenda], list[str]]:
    specs, warnings = _horarios_do_dia(config, day)
    if not specs:
        return [], warnings
    existing = {row.inicio: row for row in db.scalars(select(HorarioAgenda).where(
        HorarioAgenda.hemocentro_id == centro_id,
        HorarioAgenda.inicio.in_([start for start, _ in specs]),
    )).all()}
    rows = []
    for start, end in specs:
        row = existing.get(start)
        if row is None:
            row = HorarioAgenda(hemocentro_id=centro_id, inicio=start, fim=end,
                               capacidade=config.capacidade, ativo=True)
            db.add(row)
        else:
            row.fim = end
            row.capacidade = config.capacidade
            row.ativo = True
        rows.append(row)
    db.flush()
    return rows, warnings


def salvar_agenda(db: Session, usuario: Usuario, centro_id: int, config: AgendaConfig) -> AgendaResponse:
    _centro(db, centro_id)
    _gestor(db, usuario, centro_id)
    agenda = db.get(AgendaHemocentro, centro_id)
    versao = agenda.versao if agenda else 0
    if config.versao != versao:
        raise HTTPException(409, "A agenda mudou. Recarregue antes de salvar.")
    now = utcnow()
    reservations = db.scalars(select(Agendamento).where(
        Agendamento.hemocentro_id == centro_id, Agendamento.agendado_em > now,
        Agendamento.status != "CANCELADO",
    ).with_for_update()).all()
    counts = Counter(row.agendado_em for row in reservations)
    donors = set()
    days = {}
    for reservation in reservations:
        day = reservation.agendado_em.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(config.fuso_horario)).date()
        specs, _ = _horarios_do_dia(config, day)
        matches = dict(specs)
        previous = db.get(HorarioAgenda, reservation.horario_id) if reservation.horario_id else None
        duplicate = (reservation.doador_id, reservation.agendado_em) in donors
        if (reservation.agendado_em not in matches or counts[reservation.agendado_em] > config.capacidade
                or duplicate or (previous and previous.fim != matches[reservation.agendado_em])):
            raise HTTPException(409, f"A configuracao conflita com a reserva {reservation.id}. "
                                "Mantenha seu horario/capacidade ou regularize a reserva antes de salvar.")
        donors.add((reservation.doador_id, reservation.agendado_em))
        days[day] = None
    data = config.model_dump(mode="json", exclude={"versao"})
    if agenda is None:
        agenda = AgendaHemocentro(hemocentro_id=centro_id, versao=1, **data)
        db.add(agenda)
    else:
        for key, value in data.items():
            setattr(agenda, key, value)
        agenda.versao += 1
    for slot in db.scalars(select(HorarioAgenda).where(
        HorarioAgenda.hemocentro_id == centro_id, HorarioAgenda.inicio > now,
    )).all():
        slot.ativo = False
    db.flush()
    slots = {}
    for day in days:
        rows, _ = _materializar(db, centro_id, config, day)
        slots.update({row.inicio: row for row in rows})
    for reservation in reservations:
        if reservation.horario_id is None:
            original_version = reservation.versao
            reservation.horario_id = slots[reservation.agendado_em].id
            reservation.cancelavel_ate = reservation.agendado_em - timedelta(minutes=config.cancelamento_minutos)
            reservation.remarcavel_ate = reservation.agendado_em - timedelta(minutes=config.remarcacao_minutos)
            reservation.versao += 1
            _historico(db, reservation, usuario, "CONCILIADO", None, original_version, None,
                       reservation.agendado_em, reservation.horario_id, reservation.agendado_em)
    db.flush()
    registrar_evento(db, "AGENDA_CONFIGURADA", "sucesso", user_id=usuario.id, motivo=f"hemocentro_{centro_id}")
    return consultar_agenda(db, usuario, centro_id)


def disponibilidade(db: Session, centro_id: int, inicio: date | None, fim: date | None) -> DisponibilidadeResponse:
    centro = _centro(db, centro_id)
    config = _config(db, centro_id)
    base = {"hemocentro_id": centro_id, "fuso_horario": config.fuso_horario if config else None,
            "dias": [], "avisos": []}
    if centro.status != "ATIVO":
        return DisponibilidadeResponse(**base, situacao="INATIVO", mensagem="Unidade inativa.")
    if config is None or not config.publicada:
        return DisponibilidadeResponse(**base, situacao="SEM_AGENDA", mensagem="A unidade ainda nao publicou sua agenda.")
    now = utcnow()
    today = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(config.fuso_horario)).date()
    inicio = inicio if inicio is not None else today
    fim = fim if fim is not None else inicio + timedelta(days=6)
    if fim < inicio or (fim - inicio).days > 30:
        raise HTTPException(422, "Consulte um periodo de ate 31 dias, com inicio anterior ao fim.")
    days = []
    warnings = []
    for offset in range((fim - inicio).days + 1):
        day = inicio + timedelta(days=offset)
        if not today <= day <= today + timedelta(days=config.horizonte_dias):
            days.append(DiaDisponibilidade(data=day, motivo="Fora do periodo permitido para reservas.", horarios=[]))
            continue
        rows, notices = _materializar(db, centro_id, config, day)
        warnings.extend(notices)
        rows = [row for row in rows if row.inicio > now and row.inicio >= now + timedelta(minutes=config.antecedencia_minutos)]
        occupancy = dict(db.execute(select(Agendamento.horario_id, func.count()).where(
            Agendamento.horario_id.in_([row.id for row in rows]),
            Agendamento.status != "CANCELADO",
        ).group_by(Agendamento.horario_id)).all()) if rows else {}
        slots = [HorarioResponse(id=row.id, inicio=row.inicio, fim=row.fim,
                                 vagas_disponiveis=max(0, row.capacidade - occupancy.get(row.id, 0))) for row in rows]
        reason = None if slots else "Unidade fechada ou sem horarios dentro da antecedencia permitida."
        days.append(DiaDisponibilidade(data=day, motivo=reason, horarios=slots))
    db.commit()
    free = any(slot.vagas_disponiveis > 0 for day in days for slot in day.horarios)
    return DisponibilidadeResponse(
        hemocentro_id=centro_id, fuso_horario=config.fuso_horario,
        situacao="DISPONIVEL" if free else "SEM_VAGAS",
        mensagem="Selecione um dia e horario." if free else "Nenhuma vaga disponivel no periodo consultado.",
        dias=days, avisos=warnings,
    )


def _motivo(agendamento: Agendamento, deadline: datetime | None) -> str | None:
    if agendamento.status != "AGENDADO" or agendamento.recebido_em is not None:
        return "A reserva foi cancelada ou o atendimento ja foi recebido."
    if utcnow() >= (deadline if deadline is not None else agendamento.agendado_em):
        return "O prazo para esta alteracao terminou."
    return None


def resposta_reserva(db: Session, agendamento: Agendamento) -> ReservaResponse:
    config = _config(db, agendamento.hemocentro_id)
    centro = db.get(Hemocentro, agendamento.hemocentro_id)
    cancel_reason = _motivo(agendamento, agendamento.cancelavel_ate)
    change_reason = _motivo(agendamento, agendamento.remarcavel_ate)
    if change_reason is None and (agendamento.horario_id is None or config is None or not config.publicada
                                  or centro is None or centro.status != "ATIVO"):
        change_reason = "A unidade precisa ter agenda publicada e a reserva precisa estar conciliada."
    return ReservaResponse(
        **AgendamentoResponse.model_validate(agendamento).model_dump(),
        fuso_horario=config.fuso_horario if config else None,
        pode_cancelar=cancel_reason is None, pode_remarcar=change_reason is None,
        motivo_cancelamento=cancel_reason, motivo_remarcacao=change_reason,
        alteracoes=db.scalars(select(AlteracaoAgendamento).where(
            AlteracaoAgendamento.agendamento_id == agendamento.id,
        ).order_by(AlteracaoAgendamento.id)).all(),
    )


def _validar_horario(db: Session, slot_id: int, centro: Hemocentro) -> tuple[HorarioAgenda, AgendaConfig]:
    config = _config(db, centro.id)
    slot = db.scalar(select(HorarioAgenda).where(HorarioAgenda.id == slot_id)
                     .with_for_update().execution_options(populate_existing=True))
    if slot is None or slot.hemocentro_id != centro.id:
        raise HTTPException(404, "Horario nao encontrado nesta unidade.")
    if centro.status != "ATIVO" or config is None or not config.publicada or not slot.ativo:
        raise HTTPException(409, "Agenda indisponivel. Atualize os horarios.")
    now = utcnow()
    zone = ZoneInfo(config.fuso_horario)
    day = slot.inicio.replace(tzinfo=timezone.utc).astimezone(zone).date()
    today = now.replace(tzinfo=timezone.utc).astimezone(zone).date()
    if (slot.inicio <= now or slot.inicio < now + timedelta(minutes=config.antecedencia_minutos)
            or day > today + timedelta(days=config.horizonte_dias)):
        raise HTTPException(409, "Horario fora do prazo permitido. Atualize a disponibilidade.")
    return slot, config


def _validar_vaga(db: Session, usuario: Usuario, slot: HorarioAgenda, ignorar_id: int | None = None) -> None:
    occupied = db.scalar(select(func.count()).select_from(Agendamento).where(
        Agendamento.horario_id == slot.id, Agendamento.status != "CANCELADO",
    ))
    if occupied >= slot.capacidade:
        raise HTTPException(409, "Este horario ficou sem vagas. Escolha outro horario.")
    query = select(Agendamento.id).outerjoin(HorarioAgenda, HorarioAgenda.id == Agendamento.horario_id).where(
        Agendamento.doador_id == usuario.id, Agendamento.status != "CANCELADO",
        Agendamento.agendado_em < slot.fim,
        or_(HorarioAgenda.fim > slot.inicio,
            (Agendamento.horario_id.is_(None) & (Agendamento.agendado_em == slot.inicio))),
    )
    if ignorar_id is not None:
        query = query.where(Agendamento.id != ignorar_id)
    if db.scalar(query) is not None:
        raise HTTPException(409, "Voce ja possui um agendamento nesse intervalo.")


def _historico(db: Session, agenda: Agendamento, usuario: Usuario, acao: str, chave: str | None,
               versao: int, anterior_id: int | None, anterior: datetime,
               novo_id: int | None, novo: datetime | None) -> None:
    db.add(AlteracaoAgendamento(
        agendamento_id=agenda.id, usuario_id=usuario.id, acao=acao, chave_requisicao=chave,
        versao_origem=versao, horario_anterior_id=anterior_id, horario_novo_id=novo_id,
        agendado_anterior=anterior, agendado_novo=novo, ocorrido_em=utcnow(),
    ))


def reservar(db: Session, usuario: Usuario, data: AgendamentoCreate) -> ReservaResponse:
    centro_id = db.scalar(select(HorarioAgenda.hemocentro_id).where(HorarioAgenda.id == data.horario_id))
    if centro_id is None:
        raise HTTPException(404, "Horario nao encontrado.")
    centro = _centro(db, centro_id)
    _doador(db, usuario)
    key = str(data.chave_requisicao)
    previous = db.scalar(select(Agendamento).where(Agendamento.doador_id == usuario.id,
                                                  Agendamento.chave_requisicao == key))
    answers = [item.model_dump() for item in data.respostas_pre_triagem]
    if previous:
        original = db.scalar(select(AlteracaoAgendamento).where(
            AlteracaoAgendamento.agendamento_id == previous.id, AlteracaoAgendamento.acao == "RESERVADO",
        ))
        if original is None or original.horario_novo_id != data.horario_id or previous.respostas_pre_triagem != answers:
            raise HTTPException(409, "A chave de requisicao ja foi utilizada com outros dados.")
        return resposta_reserva(db, previous)
    slot, config = _validar_horario(db, data.horario_id, centro)
    _validar_vaga(db, usuario, slot)
    agenda = Agendamento(
        doador_id=usuario.id, hemocentro_id=centro.id, horario_id=slot.id, agendado_em=slot.inicio,
        chave_requisicao=key, respostas_pre_triagem=answers, criado_em=utcnow(), status="AGENDADO",
        versao=1, cancelavel_ate=slot.inicio - timedelta(minutes=config.cancelamento_minutos),
        remarcavel_ate=slot.inicio - timedelta(minutes=config.remarcacao_minutos),
    )
    db.add(agenda)
    db.flush()
    _historico(db, agenda, usuario, "RESERVADO", key, 0, None, slot.inicio, slot.id, slot.inicio)
    db.flush()
    # A auditoria e o commit sao o ultimo passo, ainda sob os bloqueios da reserva.
    registrar_evento(db, "AGENDAMENTO_CRIADO", "sucesso", user_id=usuario.id, atendimento_id=agenda.id)
    db.refresh(agenda)
    return resposta_reserva(db, agenda)


def _reserva_propria(db: Session, usuario: Usuario, agenda_id: int) -> tuple[Agendamento, Hemocentro]:
    centro_id = db.scalar(select(Agendamento.hemocentro_id).where(
        Agendamento.id == agenda_id, Agendamento.doador_id == usuario.id,
    ))
    if centro_id is None:
        raise HTTPException(404, "Agendamento nao encontrado.")
    centro = _centro(db, centro_id)
    _doador(db, usuario)
    agenda = db.scalar(select(Agendamento).where(Agendamento.id == agenda_id)
                       .with_for_update().execution_options(populate_existing=True))
    if agenda is None:
        raise HTTPException(404, "Agendamento nao encontrado.")
    return agenda, centro


def _repetida(db: Session, agenda: Agendamento, data: AlteracaoRequest, acao: str,
              horario_id: int | None = None) -> bool:
    previous = db.scalar(select(AlteracaoAgendamento).where(
        AlteracaoAgendamento.agendamento_id == agenda.id,
        AlteracaoAgendamento.chave_requisicao == str(data.chave_requisicao),
    ))
    if previous is None:
        return False
    if previous.acao != acao or previous.versao_origem != data.versao or previous.horario_novo_id != horario_id:
        raise HTTPException(409, "A chave de requisicao ja foi utilizada com outros dados.")
    return True


def cancelar(db: Session, usuario: Usuario, agenda_id: int, data: AlteracaoRequest) -> ReservaResponse:
    agenda, _ = _reserva_propria(db, usuario, agenda_id)
    if _repetida(db, agenda, data, "CANCELADO") or agenda.status == "CANCELADO":
        return resposta_reserva(db, agenda)
    if data.versao != agenda.versao:
        raise HTTPException(409, "O agendamento mudou. Atualize antes de cancelar.")
    reason = _motivo(agenda, agenda.cancelavel_ate)
    if reason:
        raise HTTPException(409, reason)
    _historico(db, agenda, usuario, "CANCELADO", str(data.chave_requisicao), agenda.versao,
               agenda.horario_id, agenda.agendado_em, None, None)
    agenda.status = "CANCELADO"
    agenda.cancelado_em = utcnow()
    agenda.versao += 1
    db.flush()
    registrar_evento(db, "AGENDAMENTO_CANCELADO", "sucesso", user_id=usuario.id, atendimento_id=agenda.id)
    db.refresh(agenda)
    return resposta_reserva(db, agenda)


def remarcar(db: Session, usuario: Usuario, agenda_id: int, data: RemarcacaoRequest) -> ReservaResponse:
    agenda, centro = _reserva_propria(db, usuario, agenda_id)
    if _repetida(db, agenda, data, "REMARCADO", data.horario_id):
        return resposta_reserva(db, agenda)
    if data.versao != agenda.versao:
        raise HTTPException(409, "O agendamento mudou. Atualize antes de remarcar.")
    reason = _motivo(agenda, agenda.remarcavel_ate)
    if reason:
        raise HTTPException(409, reason)
    if agenda.horario_id is None:
        raise HTTPException(409, "A reserva antiga precisa ser conciliada pela unidade antes de remarcar.")
    if data.horario_id == agenda.horario_id:
        raise HTTPException(422, "Selecione um horario diferente do atual.")
    slot, config = _validar_horario(db, data.horario_id, centro)
    _validar_vaga(db, usuario, slot, agenda.id)
    _historico(db, agenda, usuario, "REMARCADO", str(data.chave_requisicao), agenda.versao,
               agenda.horario_id, agenda.agendado_em, slot.id, slot.inicio)
    agenda.horario_id = slot.id
    agenda.agendado_em = slot.inicio
    agenda.cancelavel_ate = slot.inicio - timedelta(minutes=config.cancelamento_minutos)
    agenda.remarcavel_ate = slot.inicio - timedelta(minutes=config.remarcacao_minutos)
    agenda.versao += 1
    db.flush()
    registrar_evento(db, "AGENDAMENTO_REMARCADO", "sucesso", user_id=usuario.id, atendimento_id=agenda.id)
    db.refresh(agenda)
    return resposta_reserva(db, agenda)
