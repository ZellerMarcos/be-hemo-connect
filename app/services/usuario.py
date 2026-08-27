from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.usuario import Usuario
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate


class DuplicateUsuarioError(Exception):
    def __init__(self, field: str):
        self.field = field


def list_usuarios(db: Session) -> list[Usuario]:
    return list(db.scalars(select(Usuario).order_by(Usuario.id)).all())


def get_usuario(db: Session, usuario_id: int) -> Usuario | None:
    return db.get(Usuario, usuario_id)


def _check_duplicates(db: Session, cpf: str, email: str, usuario_id: int | None = None) -> None:
    cpf_query = select(Usuario.id).where(Usuario.cpf == cpf)
    email_query = select(Usuario.id).where(Usuario.email == email)
    if usuario_id is not None:
        cpf_query = cpf_query.where(Usuario.id != usuario_id)
        email_query = email_query.where(Usuario.id != usuario_id)
    if db.scalar(cpf_query) is not None:
        raise DuplicateUsuarioError("cpf")
    if db.scalar(email_query) is not None:
        raise DuplicateUsuarioError("email")


def create_usuario(db: Session, data: UsuarioCreate) -> Usuario:
    _check_duplicates(db, data.cpf, str(data.email))
    usuario = Usuario(**data.model_dump())
    usuario.email = str(data.email)
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise DuplicateUsuarioError("cpf ou email") from error
    db.refresh(usuario)
    return usuario


def update_usuario(db: Session, usuario: Usuario, data: UsuarioUpdate) -> Usuario:
    _check_duplicates(db, data.cpf, str(data.email), usuario.id)
    for field, value in data.model_dump().items():
        setattr(usuario, field, str(value) if field == "email" else value)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise DuplicateUsuarioError("cpf ou email") from error
    db.refresh(usuario)
    return usuario


def delete_usuario(db: Session, usuario: Usuario) -> None:
    db.delete(usuario)
    db.commit()