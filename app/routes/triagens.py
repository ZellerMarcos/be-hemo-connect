from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.triagem import Agendamento
from app.models.usuario import Usuario
from app.schemas.triagem import (
    AgendamentoCreate, AgendamentoResponse, AvaliacaoUpdate, FilaResponse,
    HistoricoItem, IndicadoresResponse, TriagemDetalhe, TriagemFinalizar, TriagemStatus,
)
from app.security.authorization import require_roles
from app.services import triagem as service


router = APIRouter(tags=["Atendimento"])
enfermeiro = require_roles("ENFERMEIRO")
doador = require_roles("DOADOR")
recepcao = require_roles("RECEPCIONISTA", "RESPONSAVEL_HEMOCENTRO", "ADMINISTRADOR")


@router.get("/triagens/indicadores", response_model=IndicadoresResponse)
def dashboard(db: Session = Depends(get_db), usuario: Usuario = Depends(enfermeiro)):
    return service.indicadores(db, usuario)


@router.get("/triagens", response_model=FilaResponse)
def fila(
    pagina: int = Query(1, ge=1), tamanho: int = Query(20, ge=1, le=100),
    status: TriagemStatus | None = None, busca: str | None = Query(None, max_length=100),
    inicio: date | None = None, fim: date | None = None,
    db: Session = Depends(get_db), usuario: Usuario = Depends(enfermeiro),
):
    return service.list_fila(db, usuario, pagina, tamanho, status=status, busca=busca, inicio=inicio, fim=fim)


@router.get("/triagens/{agendamento_id}", response_model=TriagemDetalhe)
def detalhes(agendamento_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(enfermeiro)):
    return service.detalhe(db, usuario, agendamento_id)


@router.post("/triagens/{agendamento_id}/iniciar", response_model=TriagemDetalhe)
def iniciar(agendamento_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(enfermeiro)):
    return service.iniciar(db, usuario, agendamento_id)


@router.put("/triagens/{agendamento_id}", response_model=TriagemDetalhe)
def salvar(agendamento_id: int, data: AvaliacaoUpdate,
           db: Session = Depends(get_db), usuario: Usuario = Depends(enfermeiro)):
    return service.salvar_avaliacao(db, usuario, agendamento_id, data)


@router.post("/triagens/{agendamento_id}/finalizar", response_model=TriagemDetalhe)
def finalizar(agendamento_id: int, data: TriagemFinalizar,
              db: Session = Depends(get_db), usuario: Usuario = Depends(enfermeiro)):
    return service.salvar_avaliacao(db, usuario, agendamento_id, data, finalizar=True)


@router.post("/agendamentos", response_model=AgendamentoResponse, status_code=201)
def agendar(data: AgendamentoCreate, db: Session = Depends(get_db), usuario: Usuario = Depends(doador)):
    return service.create_agendamento(db, usuario, data)


@router.get("/agendamentos/me", response_model=list[AgendamentoResponse])
def meus_agendamentos(db: Session = Depends(get_db), usuario: Usuario = Depends(doador)):
    return db.scalars(select(Agendamento).where(Agendamento.doador_id == usuario.id)
                      .order_by(Agendamento.agendado_em.desc())).all()


@router.get("/historico/me", response_model=list[HistoricoItem])
def meu_historico(db: Session = Depends(get_db), usuario: Usuario = Depends(doador)):
    return service.historico(db, usuario, usuario.id)


@router.get("/recepcao/agendamentos", response_model=FilaResponse)
def fila_recepcao(pagina: int = Query(1, ge=1), tamanho: int = Query(20, ge=1, le=100),
                 db: Session = Depends(get_db), usuario: Usuario = Depends(recepcao)):
    return service.list_fila(db, usuario, pagina, tamanho, status="AGENDADO", recepcao=True)


@router.post("/recepcao/agendamentos/{agendamento_id}/receber", response_model=AgendamentoResponse)
def receber(agendamento_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(recepcao)):
    return service.receber(db, usuario, agendamento_id)
