from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.usuario import Usuario
from app.security.session import issue_session


def auth_headers(engine, email: str = "joao@example.com") -> dict[str, str]:
    with Session(engine) as db:
        usuario = db.scalar(select(Usuario).where(Usuario.email == email))
        if usuario is None:
            return {"Authorization": "Bearer nonexistent-test-user"}
        return {"Authorization": f"Bearer {issue_session(db, usuario)}"}
