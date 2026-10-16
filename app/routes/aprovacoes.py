from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.usuario import AprovarEnfermeiroRequest, AprovacoesPendentesResponse, UsuarioResponse
from app.security.authorization import require_roles
from app.services.aprovacoes import aprovar_enfermeiro, listar_pendentes


router = APIRouter(prefix="/usuarios/aprovacoes", tags=["Aprovação de enfermeiros"])
administrador = require_roles("ADMINISTRADOR")


@router.get("/pendentes", response_model=AprovacoesPendentesResponse)
def pendentes(pagina: int = Query(1, ge=1), tamanho: int = Query(20, ge=1, le=100),
              db: Session = Depends(get_db), _: Usuario = Depends(administrador)):
    return listar_pendentes(db, pagina, tamanho)


@router.post("/{usuario_id}/aprovar", response_model=UsuarioResponse)
def aprovar(usuario_id: int, data: AprovarEnfermeiroRequest,
            db: Session = Depends(get_db), actor: Usuario = Depends(administrador)):
    return aprovar_enfermeiro(db, actor, usuario_id, data)
