from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hemocentro import Hemocentro
from app.schemas.hemocentro import HemocentroCreate, HemocentroUpdate


def list_hemocentros(db: Session) -> list[Hemocentro]:
    return list(db.scalars(select(Hemocentro).order_by(Hemocentro.id)).all())


def get_hemocentro(db: Session, hemocentro_id: int) -> Hemocentro | None:
    return db.get(Hemocentro, hemocentro_id)


def create_hemocentro(db: Session, data: HemocentroCreate) -> Hemocentro:
    hemocentro = Hemocentro(**data.model_dump())
    db.add(hemocentro)
    db.commit()
    db.refresh(hemocentro)
    return hemocentro


def update_hemocentro(
    db: Session, hemocentro: Hemocentro, data: HemocentroUpdate
) -> Hemocentro:
    for field, value in data.model_dump().items():
        setattr(hemocentro, field, value)
    db.commit()
    db.refresh(hemocentro)
    return hemocentro


def delete_hemocentro(db: Session, hemocentro: Hemocentro) -> None:
    db.delete(hemocentro)
    db.commit()