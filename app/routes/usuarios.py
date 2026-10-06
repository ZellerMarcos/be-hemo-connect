from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.routes.auth import require_active_session
from app.models.usuario import Usuario
from app.models.hemocentro import Hemocentro
from app.security.session import authenticate_session
from app.services.privacidade import excluir_dados_titular
from app.schemas.usuario import EnfermeiroSolicitacao, UsuarioCreate, UsuarioResponse, UsuarioUpdate
from app.services.usuario import (
    DuplicateUsuarioError,
    create_usuario,
    get_usuario,
    list_usuarios,
    update_usuario,
)


router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


def require_owner_or_admin(usuario: Usuario, usuario_id: int) -> None:
    if usuario.perfil != "ADMINISTRADOR" and usuario.id != usuario_id:
        raise HTTPException(403, "Sem permissão para acessar este usuário.")


def find_or_404(db: Session, usuario_id: int):
    # Busca o usuário pelo ID e gera 404 quando ele não existe.
    usuario = get_usuario(db, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return usuario


def handle_duplicate(error: DuplicateUsuarioError) -> None:
    # Centraliza a resposta de conflito quando CPF ou e-mail já estão em uso.
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Já existe um usuário com este {error.field}.",
    ) from error


@router.get("", response_model=list[UsuarioResponse])
def read_usuarios(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_active_session),
):
    # Lista usuários somente se a sessão estiver ativa dentro do limite de inatividade.
    return list_usuarios(db) if usuario.perfil == "ADMINISTRADOR" else [usuario]


@router.get("/{usuario_id}", response_model=UsuarioResponse)
def read_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_active_session),
):
    # Consulta individual também precisa passar pela verificação de sessão ativa.
    require_owner_or_admin(usuario, usuario_id)
    return find_or_404(db, usuario_id)


@router.post("/solicitar-enfermagem", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def solicitar_enfermagem(data: EnfermeiroSolicitacao, db: Session = Depends(get_db)):
    if not data.consentimento_aceito:
        raise HTTPException(422, "O consentimento explicito e obrigatorio para concluir o cadastro.")
    try:
        return create_usuario(db, data, aprovacao_pendente=True)
    except DuplicateUsuarioError as error:
        handle_duplicate(error)


@router.post("", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def create_usuario_route(
    data: UsuarioCreate, db: Session = Depends(get_db),
    authorization: Annotated[str | None, Header()] = None,
):
    # Criação de usuário continua sem exigir sessão porque é o ponto de entrada do cadastro.
    # O consentimento explicito bloqueia cadastro silencioso sem aceite do titular.
    if not data.consentimento_aceito:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O consentimento explicito e obrigatorio para concluir o cadastro.",
        )
    if data.perfil != "DOADOR" or data.status != "ATIVO" or data.hemocentro_id is not None:
        actor = authenticate_session(db, authorization)
        if actor.perfil != "ADMINISTRADOR":
            raise HTTPException(403, "Somente administradores podem cadastrar profissionais.")
    if data.perfil not in ("DOADOR", "ADMINISTRADOR") and data.hemocentro_id is None:
        raise HTTPException(422, "Profissionais precisam de vínculo com um hemocentro.")
    if data.hemocentro_id is not None and db.get(Hemocentro, data.hemocentro_id) is None:
        raise HTTPException(422, "Hemocentro não encontrado.")
    try:
        return create_usuario(db, data)
    except DuplicateUsuarioError as error:
        handle_duplicate(error)


@router.put("/{usuario_id}", response_model=UsuarioResponse)
def update_usuario_route(
    usuario_id: int,
    data: UsuarioUpdate,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(require_active_session),
):
    # Alteração de usuário exige sessão ativa para evitar ações indevidas após timeout.
    require_owner_or_admin(actor, usuario_id)
    usuario = find_or_404(db, usuario_id)
    if usuario.aprovacao_pendente and (
        data.status != "INATIVO" or data.perfil != "ENFERMEIRO"
        or data.hemocentro_id != usuario.hemocentro_id
    ):
        raise HTTPException(409, "Use o painel de aprovação para liberar este enfermeiro.")
    if actor.perfil != "ADMINISTRADOR" and (
        data.perfil != usuario.perfil or data.status != usuario.status
        or data.hemocentro_id != usuario.hemocentro_id
    ):
        raise HTTPException(403, "Não é permitido alterar perfil, status ou vínculo institucional.")
    if data.perfil not in ("DOADOR", "ADMINISTRADOR") and data.hemocentro_id is None:
        raise HTTPException(422, "Profissionais precisam de vínculo com um hemocentro.")
    if data.hemocentro_id is not None and db.get(Hemocentro, data.hemocentro_id) is None:
        raise HTTPException(422, "Hemocentro não encontrado.")
    try:
        return update_usuario(db, usuario, data)
    except DuplicateUsuarioError as error:
        handle_duplicate(error)


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_usuario_route(
    usuario_id: int,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(require_active_session),
):
    # Exclusão também é protegida pela mesma checagem de sessão ativa e inatividade.
    require_owner_or_admin(actor, usuario_id)
    usuario = find_or_404(db, usuario_id)
    # Preserva vínculos de atendimentos e autoria, como a exclusão LGPD.
    excluir_dados_titular(db, usuario)