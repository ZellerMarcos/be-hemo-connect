from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.routes.auth import require_active_session
from app.schemas.usuario import UsuarioCreate, UsuarioResponse, UsuarioUpdate
from app.services.usuario import (
    DuplicateUsuarioError,
    create_usuario,
    delete_usuario,
    get_usuario,
    list_usuarios,
    update_usuario,
)


router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


def find_or_404(db: Session, usuario_id: int):
    usuario = get_usuario(db, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return usuario


def handle_duplicate(error: DuplicateUsuarioError) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Já existe um usuário com este {error.field}.",
    ) from error


@router.get("", response_model=list[UsuarioResponse])
def read_usuarios(
    db: Session = Depends(get_db),
    _: object = Depends(require_active_session),
):
    return list_usuarios(db)


@router.get("/{usuario_id}", response_model=UsuarioResponse)
def read_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_active_session),
):
    return find_or_404(db, usuario_id)


@router.post("", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def create_usuario_route(data: UsuarioCreate, db: Session = Depends(get_db)):
    try:
        return create_usuario(db, data)
    except DuplicateUsuarioError as error:
        handle_duplicate(error)


@router.put("/{usuario_id}", response_model=UsuarioResponse)
def update_usuario_route(
    usuario_id: int,
    data: UsuarioUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_active_session),
):
    usuario = find_or_404(db, usuario_id)
    try:
        return update_usuario(db, usuario, data)
    except DuplicateUsuarioError as error:
        handle_duplicate(error)


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_usuario_route(
    usuario_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_active_session),
):
    usuario = find_or_404(db, usuario_id)
    delete_usuario(db, usuario)