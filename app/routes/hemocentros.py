from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.routes.auth import require_active_session
from app.schemas.hemocentro import (
    HemocentroCreate,
    HemocentroResponse,
    HemocentroUpdate,
)
from app.services.hemocentro import (
    create_hemocentro,
    delete_hemocentro,
    get_hemocentro,
    list_hemocentros,
    update_hemocentro,
)


router = APIRouter(prefix="/hemocentros", tags=["Hemocentros"])


def find_or_404(db: Session, hemocentro_id: int):
    # Busca de hemocentro por ID: responde 404 quando o registro não existe.
    hemocentro = get_hemocentro(db, hemocentro_id)
    if hemocentro is None:
        raise HTTPException(status_code=404, detail="Hemocentro não encontrado")
    return hemocentro


@router.get("", response_model=list[HemocentroResponse])
def read_hemocentros(
    db: Session = Depends(get_db),
    _: object = Depends(require_active_session),
):
    # Qualquer leitura de dados protegidos só ocorre enquanto a sessão está ativa.
    return list_hemocentros(db)


@router.get("/{hemocentro_id}", response_model=HemocentroResponse)
def read_hemocentro(
    hemocentro_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_active_session),
):
    # A consulta individual também passa pela checagem do timeout de inatividade do backend.
    return find_or_404(db, hemocentro_id)


@router.post("", response_model=HemocentroResponse, status_code=status.HTTP_201_CREATED)
def create_hemocentro_route(
    data: HemocentroCreate,
    db: Session = Depends(get_db),
    _: object = Depends(require_active_session),
):
    # Criação de hemocentro precisa de sessão válida para evitar ações sem usuário autenticado.
    return create_hemocentro(db, data)


@router.put("/{hemocentro_id}", response_model=HemocentroResponse)
def update_hemocentro_route(
    hemocentro_id: int,
    data: HemocentroUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_active_session),
):
    # Atualização de dados protegidos só é permitida quando a sessão continua ativa.
    hemocentro = find_or_404(db, hemocentro_id)
    return update_hemocentro(db, hemocentro, data)


@router.delete("/{hemocentro_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hemocentro_route(
    hemocentro_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_active_session),
):
    # Exclusão também depende de sessão ativa para cumprir o limite de inatividade do backend.
    hemocentro = find_or_404(db, hemocentro_id)
    delete_hemocentro(db, hemocentro)