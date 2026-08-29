from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hemocentro import Hemocentro
from app.schemas.hemocentro import HemocentroCreate, HemocentroUpdate


def list_hemocentros(db: Session) -> list[Hemocentro]:
    # Lista os hemocentros em ordem de cadastro para facilitar a consulta e a apresentação.
    return list(db.scalars(select(Hemocentro).order_by(Hemocentro.id)).all())


def get_hemocentro(db: Session, hemocentro_id: int) -> Hemocentro | None:
    # Busca direta por ID para validar se o hemocentro existe antes de operar no registro.
    return db.get(Hemocentro, hemocentro_id)


def create_hemocentro(db: Session, data: HemocentroCreate) -> Hemocentro:
    # Cria um novo hemocentro a partir do payload validado pela API.
    hemocentro = Hemocentro(**data.model_dump())
    db.add(hemocentro)
    db.commit()
    db.refresh(hemocentro)
    return hemocentro


def update_hemocentro(
    db: Session, hemocentro: Hemocentro, data: HemocentroUpdate
) -> Hemocentro:
    # Atualiza apenas os campos enviados, preservando o restante do registro intacto.
    for field, value in data.model_dump().items():
        setattr(hemocentro, field, value)
    db.commit()
    db.refresh(hemocentro)
    return hemocentro


def delete_hemocentro(db: Session, hemocentro: Hemocentro) -> None:
    # Remove o registro do banco após confirmar sua existência e validade da requisição.
    db.delete(hemocentro)
    db.commit()