from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.usuario import Usuario
from app.security.password import verify_password


def authenticate_user(db: Session, email: str, password: str) -> Usuario | None:
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None or usuario.status != "ATIVO":
        return None
    if not verify_password(password, usuario.senha_hash):
        return None
    return usuario