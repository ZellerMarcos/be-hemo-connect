from sqlalchemy import select
from sqlalchemy.orm import Session
from httpx import Response

from app.models.usuario import Usuario
from app.security.session import issue_session


def auth_headers(engine, email: str = "joao@example.com") -> dict[str, str]:
    with Session(engine) as db:
        usuario = db.scalar(select(Usuario).where(Usuario.email == email))
        if usuario is None:
            return {"Authorization": "Bearer nonexistent-test-user"}
        return {"Authorization": f"Bearer {issue_session(db, usuario)}"}


def two_factor_payload(response: Response, code: str) -> dict[str, str]:
    body = response.json()
    assert response.status_code == 200
    return {
        "challenge_id": body["challenge_id"],
        "challenge_secret": body["challenge_secret"],
        "code": code,
    }
