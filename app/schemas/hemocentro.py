from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


HemocentroStatus = Literal["ATIVO", "INATIVO"]


class HemocentroBase(BaseModel):
    nome: str = Field(min_length=1)
    endereco: str = Field(min_length=1)
    telefone: str = Field(min_length=1)
    status: HemocentroStatus


class HemocentroCreate(HemocentroBase):
    pass


class HemocentroUpdate(HemocentroBase):
    pass


class HemocentroResponse(HemocentroBase):
    model_config = ConfigDict(from_attributes=True)

    id: int