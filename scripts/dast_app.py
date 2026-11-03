import json
import os
import secrets
from pathlib import Path
from threading import Lock

from sqlalchemy.engine import make_url


SYNTHETIC_RECIPIENTS = {"doador@example.com", "administrador@example.com"}


def validate_environment() -> Path:
    if os.environ.get("HEMO_DAST_ISOLATED") != "1" or os.environ.get("APP_ENV") != "ci":
        raise RuntimeError("DAST factory is restricted to explicitly isolated CI.")
    url = make_url(os.environ.get("DATABASE_URL", ""))
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.database != "hemo_dast"
        or url.username != "hemo_dast"
    ):
        raise RuntimeError("DAST requires the disposable loopback hemo_dast PostgreSQL database.")
    directory = Path(os.environ["DAST_PRIVATE_DIR"]).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def create_app():
    directory = validate_environment()
    from app.database import engine
    from app.main import app
    from app.models import Hemocentro, Usuario
    from app.models.hemocentro import Base
    from app.security.password import hash_password
    from app.services import email
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    lock = Lock()
    outbox = directory / "outbox.json"
    outbox.write_text("[]", encoding="utf-8")

    def capture_email(recipient: str, subject: str, body: str) -> None:
        if recipient not in SYNTHETIC_RECIPIENTS:
            raise RuntimeError("DAST mail adapter accepts only the two synthetic example.com accounts.")
        with lock:
            messages = json.loads(outbox.read_text(encoding="utf-8"))
            messages.append({"recipient": recipient, "subject": subject, "body": body})
            outbox.write_text(json.dumps(messages), encoding="utf-8")

    email._send_email = capture_email
    Base.metadata.create_all(engine)
    credentials = []
    with Session(engine) as db:
        if db.scalar(select(Usuario.id).limit(1)) is not None:
            raise RuntimeError("DAST bootstrap requires an empty disposable database.")
        centro = Hemocentro(nome="CI Centro", endereco="Synthetic address",
                            telefone="0000000000", status="ATIVO")
        db.add(centro)
        db.flush()
        for index, role in enumerate(("DOADOR", "ADMINISTRADOR"), start=1):
            password = secrets.token_urlsafe(32)
            address = f"{role.lower()}@example.com"
            db.add(Usuario(nome=f"CI {role}", cpf=f"{index:011d}", email=address,
                           senha_hash=hash_password(password), perfil=role, status="ATIVO",
                           hemocentro_id=centro.id if role == "ADMINISTRADOR" else None))
            credentials.append({"role": role.lower(), "email": address, "password": password})
        db.commit()
    (directory / "credentials.json").write_text(json.dumps(credentials), encoding="utf-8")
    return app
