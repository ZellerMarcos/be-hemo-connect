from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


HemocentroStatus = Literal["ATIVO", "INATIVO"]


class HemocentroBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nome: str = Field(min_length=1, max_length=255)
    endereco: str = Field(min_length=1, max_length=500)
    telefone: str = Field(min_length=1, max_length=30)
    status: HemocentroStatus


class HemocentroCreate(HemocentroBase):
    pass


class HemocentroUpdate(HemocentroBase):
    pass


class HemocentroResponse(HemocentroBase):
    model_config = ConfigDict(from_attributes=True)

    id: int