from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


TextoResposta = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2000)]
Identificador = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=80)]


class Opcao(BaseModel):
    valor: str
    rotulo: str


class Dependencia(BaseModel):
    id: str
    valores: list[str]


class Pergunta(BaseModel):
    id: str
    texto: str
    secao: Literal["geral", "confidencial"] = "geral"
    tipo: Literal["escolha", "numero", "texto", "data", "multipla"] = "escolha"
    obrigatoria: bool = True
    opcoes: list[Opcao] = Field(default_factory=list)
    depende_de: Dependencia | None = None


class Confirmacao(BaseModel):
    id: str
    texto: str


class CatalogoQuestionario(BaseModel):
    versao: str
    versao_aviso: str
    publicado: bool
    aviso: str
    confirmacoes: list[Confirmacao]
    perguntas: list[Pergunta]


class RespostaQuestionario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Identificador
    valores: list[TextoResposta] = Field(min_length=1, max_length=10)


class QuestionarioSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    versao: Identificador
    versao_aviso: Identificador
    respostas: list[RespostaQuestionario] = Field(min_length=1, max_length=80)
    confirmacoes: list[Identificador] = Field(min_length=1, max_length=3)


class MetadadosPreTriagem(BaseModel):
    versao: str
    versao_aviso: str
    enviado_em: datetime
    confirmacoes: list[str]


class QuestionarioRegistrado(QuestionarioSubmission):
    enviado_em: datetime


class UltimoQuestionario(BaseModel):
    encontrado: bool
    compativel: bool
    versao: str | None = None
    versao_aviso: str | None = None
    enviado_em: datetime | None = None
    respostas: list[RespostaQuestionario] = Field(default_factory=list)
