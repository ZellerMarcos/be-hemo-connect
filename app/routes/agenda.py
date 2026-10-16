from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.routes.auth import require_active_session
from app.schemas.agenda import (
    AgendaConfig, AgendaResponse, AlteracaoRequest, DisponibilidadeResponse, RemarcacaoRequest, ReservaResponse,
)
from app.security.authorization import require_roles
from app.services import agenda as service


router = APIRouter(tags=["Agenda e reservas"])
gestor = require_roles("ADMINISTRADOR", "RESPONSAVEL_HEMOCENTRO")
doador = require_roles("DOADOR")


@router.get("/hemocentros/{centro_id}/agenda", response_model=AgendaResponse)
def consultar(centro_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(gestor)):
    return service.consultar_agenda(db, usuario, centro_id)


@router.put("/hemocentros/{centro_id}/agenda", response_model=AgendaResponse)
def configurar(centro_id: int, data: AgendaConfig, db: Session = Depends(get_db), usuario: Usuario = Depends(gestor)):
    return service.salvar_agenda(db, usuario, centro_id, data)


@router.get("/hemocentros/{centro_id}/disponibilidade", response_model=DisponibilidadeResponse)
def disponibilidade(centro_id: int, inicio: date | None = None, fim: date | None = None,
                    db: Session = Depends(get_db), _: Usuario = Depends(require_active_session)):
    return service.disponibilidade(db, centro_id, inicio, fim)


@router.post("/agendamentos/{agenda_id}/cancelar", response_model=ReservaResponse)
def cancelar(agenda_id: int, data: AlteracaoRequest, db: Session = Depends(get_db), usuario: Usuario = Depends(doador)):
    return service.cancelar(db, usuario, agenda_id, data)


@router.post("/agendamentos/{agenda_id}/remarcar", response_model=ReservaResponse)
def remarcar(agenda_id: int, data: RemarcacaoRequest, db: Session = Depends(get_db), usuario: Usuario = Depends(doador)):
    return service.remarcar(db, usuario, agenda_id, data)
