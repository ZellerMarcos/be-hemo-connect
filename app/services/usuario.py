from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.usuario import Usuario
from app.security.password import hash_password
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate


class DuplicateUsuarioError(Exception):
    # Exceção de domínio para indicar conflito de CPF ou e-mail ao persistir um usuário.
    def __init__(self, field: str):
        self.field = field


def list_usuarios(db: Session) -> list[Usuario]:
    # Retorna todos os usuários ordenados por ID para manter uma listagem previsível.
    return list(db.scalars(select(Usuario).order_by(Usuario.id)).all())


def get_usuario(db: Session, usuario_id: int) -> Usuario | None:
    # Busca direta por ID para validar existência antes de atualizar ou excluir o registro.
    return db.get(Usuario, usuario_id)


def _check_duplicates(db: Session, cpf: str, email: str, usuario_id: int | None = None) -> None:
    # Garante que CPF e e-mail sejam únicos, ignorando o próprio usuário em edições.
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
    # Cria um usuário novo com senha separada do restante dos dados e depois aplica hash.
    _check_duplicates(db, data.cpf, str(data.email))
    usuario_data = data.model_dump(exclude={"senha"})
    usuario_data["senha_hash"] = hash_password(data.senha)
    usuario = Usuario(**usuario_data)
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
    # Atualiza os campos do usuário respeitando regras de unicidade e preservando as demais informações.
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
    # Remove o usuário do banco, encerrando o registro após a confirmação de existência.
    db.delete(usuario)
    db.commit()