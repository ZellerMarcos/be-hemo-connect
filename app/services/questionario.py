import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.triagem import Agendamento
from app.models.usuario import Usuario
from app.schemas.questionario import (
    CatalogoQuestionario, Confirmacao, Dependencia, MetadadosPreTriagem, Opcao,
    Pergunta, QuestionarioSubmission, UltimoQuestionario,
)


VERSAO = "pre-triagem-v1"
VERSAO_AVISO = "pre-triagem-privacidade-v1"
SIM_NAO = [Opcao(valor="sim", rotulo="Sim"), Opcao(valor="nao", rotulo="Não")]
DESCONHECIDO = Opcao(valor="desconhecido", rotulo="Não sei informar")
RESERVADO = Opcao(valor="reservado", rotulo="Prefiro conversar com o profissional")
NAO_APLICA = Opcao(valor="nao_se_aplica", rotulo="Não se aplica")


def escolha(id: str, texto: str, *, confidencial: bool = False,
            depende_de: Dependencia | None = None) -> Pergunta:
    return Pergunta(
        id=id, texto=texto, secao="confidencial" if confidencial else "geral",
        opcoes=[*SIM_NAO, DESCONHECIDO, RESERVADO], depende_de=depende_de,
    )


def complemento(id: str, texto: str, principal: str, *, tipo: Literal["texto", "data"] = "texto",
                confidencial: bool = False, obrigatoria: bool = False) -> Pergunta:
    return Pergunta(
        id=id, texto=texto, tipo=tipo, obrigatoria=obrigatoria,
        secao="confidencial" if confidencial else "geral",
        depende_de=Dependencia(id=principal, valores=["sim"]),
    )


PERGUNTAS = [
    Pergunta(id="peso", texto="Qual é seu peso atual, em kg?", tipo="numero"),
    escolha("doacao_anterior", "Você já doou sangue?"),
    complemento("ultima_doacao", "Data da última doação (ou não sei informar)", "doacao_anterior",
                tipo="data", obrigatoria=True),
    complemento("unidade_anterior", "Em qual hemocentro você doou? (opcional)", "doacao_anterior"),
    escolha("reacao_anterior", "Você teve mal-estar ou alguma reação durante ou após uma doação?",
            depende_de=Dependencia(id="doacao_anterior", valores=["sim"])),
    complemento("reacao_detalhe", "Deseja descrever a reação? (opcional)", "reacao_anterior"),
    escolha("sintomas", "Você apresenta febre, mal-estar ou sintomas de infecção atualmente?"),
    complemento("sintomas_detalhe", "Deseja informar quais sintomas? (opcional)", "sintomas"),
    escolha("tratamento", "Você está realizando algum tratamento médico?"),
    complemento("tratamento_detalhe", "Deseja informar o tratamento? (opcional)", "tratamento"),
    escolha("condicao_saude", "Você possui alguma condição de saúde diagnosticada a informar para esta avaliação?"),
    complemento("condicao_detalhe", "Deseja informar a condição? (opcional)", "condicao_saude"),
    escolha("medicamentos", "Você usa medicamentos atualmente ou deseja informar algum uso anterior?"),
    complemento("medicamentos_detalhe", "Nome e período de uso, se souber (opcional)", "medicamentos"),
    complemento("medicamentos_dose", "Dosagem, se souber (opcional)", "medicamentos"),
    escolha("vacinas", "Você deseja informar alguma vacinação para a avaliação desta doação?"),
    complemento("vacina_nome", "Qual vacina? (opcional)", "vacinas"),
    complemento("vacina_data", "Data da vacinação (ou não sei informar)", "vacinas",
                tipo="data", obrigatoria=True),
    Pergunta(
        id="procedimentos", tipo="multipla",
        texto="Quais procedimentos do seu histórico você precisa informar para esta avaliação?",
        opcoes=[
            Opcao(valor="cirurgia", rotulo="Cirurgia ou procedimento médico"),
            Opcao(valor="tatuagem", rotulo="Tatuagem ou piercing"),
            Opcao(valor="transfusao", rotulo="Transfusão de sangue"),
            Opcao(valor="nenhum", rotulo="Nenhum"), DESCONHECIDO, RESERVADO,
        ],
    ),
    Pergunta(
        id="procedimento_data", texto="Data do procedimento mais recente (ou não sei informar)",
        tipo="data", depende_de=Dependencia(id="procedimentos", valores=["cirurgia", "tatuagem", "transfusao"]),
    ),
    escolha("viagens", "Você deseja informar alguma viagem para a avaliação desta doação?"),
    complemento("viagem_local", "Local e período da viagem, se souber (opcional)", "viagens"),
    Pergunta(
        id="gestacao", secao="confidencial",
        texto="Você está grávida ou existe possibilidade de gravidez?",
        opcoes=[
            Opcao(valor="confirmada", rotulo="Gravidez confirmada"),
            Opcao(valor="possibilidade", rotulo="Existe possibilidade"),
            Opcao(valor="nao", rotulo="Não"), DESCONHECIDO, NAO_APLICA, RESERVADO,
        ],
    ),
    Pergunta(
        id="amamentacao", secao="confidencial", texto="Você está amamentando?",
        opcoes=[*SIM_NAO, NAO_APLICA, RESERVADO],
    ),
    Pergunta(
        id="parto_aborto", secao="confidencial",
        texto="Você deseja informar parto ou interrupção de gestação para esta avaliação?",
        opcoes=[*SIM_NAO, NAO_APLICA, RESERVADO],
    ),
    complemento("parto_data", "Data, se desejar informar (opcional)", "parto_aborto",
                tipo="data", confidencial=True),
    escolha("prep_pep", "Você usa ou usou PrEP ou PEP, medicamentos de prevenção ao HIV?",
            confidencial=True),
    complemento("prep_detalhe", "Nome e período de uso, se desejar informar (opcional)", "prep_pep",
                confidencial=True),
    escolha("exposicoes", "Há alguma situação de exposição que você deseja informar para avaliação de infecções transmitidas pelo sangue?",
            confidencial=True),
    Pergunta(
        id="outras_informacoes", tipo="texto", secao="confidencial", obrigatoria=False,
        texto="Deseja acrescentar alguma informação para a equipe? Não inclua dados de terceiros. (opcional)",
    ),
]
CONFIRMACOES = [
    Confirmacao(id="veracidade", texto="Respondi conforme as informações que conheço e posso esclarecer respostas com o profissional."),
    Confirmacao(id="avaliacao_presencial", texto="Entendo que este formulário não substitui a entrevista e a avaliação presencial."),
    Confirmacao(id="ciencia_privacidade", texto="Li o aviso sobre finalidade, acesso e tratamento dos dados de saúde."),
]


def catalogo() -> CatalogoQuestionario:
    controlador = os.getenv("PRIVACIDADE_CONTROLADOR", "").strip()
    canal = os.getenv("PRIVACIDADE_CANAL", "").strip()
    if not controlador or not canal:
        raise HTTPException(503, "A instituição precisa configurar o controlador e o canal de privacidade da pré-triagem.")
    aviso = (
        "Estas perguntas incluem dados sensíveis de saúde. As respostas serão usadas na sua "
        "pré-triagem e no atendimento pelo hemocentro escolhido. Você pode consultar e exportar "
        "seus dados na área Privacidade. A enfermagem autorizada da unidade pode consultar as "
        "respostas no fluxo do atendimento, após sua chegada. A recepção não recebe as respostas "
        "neste formulário. Nas perguntas íntimas, você pode escolher 'Prefiro conversar com o "
        "profissional', sem impedir o agendamento. Não inclua dados de terceiros. "
        "As respostas não definem sua aptidão para doar. Mudanças na sua saúde até a doação "
        "devem ser informadas à equipe. A confirmação abaixo registra ciência deste aviso, "
        "não autorização genérica para outros usos. Para correção após o envio e demais "
        "direitos, utilize o canal institucional e consulte a política de privacidade."
    )
    if controlador and canal:
        aviso += f" Controlador: {controlador}. Canal de privacidade: {canal}."
    return CatalogoQuestionario(
        versao=VERSAO, versao_aviso=VERSAO_AVISO, publicado=True, aviso=aviso,
        confirmacoes=CONFIRMACOES, perguntas=PERGUNTAS,
    )


def ultima_resposta(db: Session, usuario: Usuario, hemocentro_id: int) -> UltimoQuestionario:
    catalogo_atual = catalogo()
    envelope = db.scalar(
        select(Agendamento.questionario_pre_triagem)
        .where(
            Agendamento.doador_id == usuario.id,
            Agendamento.hemocentro_id == hemocentro_id,
            Agendamento.questionario_pre_triagem.is_not(None),
        )
        .order_by(Agendamento.criado_em.desc(), Agendamento.id.desc())
        .limit(1)
    )
    if not isinstance(envelope, dict):
        return UltimoQuestionario(encontrado=False, compativel=False)

    compativel = (
        envelope.get("versao") == catalogo_atual.versao
        and envelope.get("versao_aviso") == catalogo_atual.versao_aviso
    )
    respostas = envelope.get("respostas", []) if compativel else []
    return UltimoQuestionario(
        encontrado=True,
        compativel=compativel,
        versao=envelope.get("versao") if isinstance(envelope.get("versao"), str) else None,
        versao_aviso=envelope.get("versao_aviso") if isinstance(envelope.get("versao_aviso"), str) else None,
        enviado_em=envelope.get("enviado_em"),
        respostas=respostas,
    )


def canonico(data: QuestionarioSubmission) -> dict[str, object]:
    return {
        "versao": data.versao, "versao_aviso": data.versao_aviso,
        "respostas": [
            {"id": item.id, "valores": sorted(item.valores)}
            for item in sorted(data.respostas, key=lambda item: item.id)
        ],
        "confirmacoes": sorted(data.confirmacoes),
    }


def validar(data: QuestionarioSubmission) -> list[dict[str, str]]:
    atual = catalogo()
    if data.versao != atual.versao or data.versao_aviso != atual.versao_aviso:
        raise HTTPException(409, "O questionário ou aviso foi atualizado. Recarregue e revise suas respostas antes de enviar.")
    ids = [item.id for item in data.respostas]
    if len(ids) != len(set(ids)) or set(ids) - {item.id for item in PERGUNTAS}:
        raise HTTPException(422, "O questionário contém perguntas duplicadas ou desconhecidas.")
    obrigatorias = {item.id for item in CONFIRMACOES}
    if len(data.confirmacoes) != len(set(data.confirmacoes)) or set(data.confirmacoes) != obrigatorias:
        raise HTTPException(422, "Confirme a veracidade, a avaliação presencial e a ciência do aviso de privacidade.")
    respostas = {item.id: item.valores for item in data.respostas}
    snapshot = []
    visiveis: set[str] = set()
    for pergunta in PERGUNTAS:
        dependencia = pergunta.depende_de
        visivel = dependencia is None or (
            dependencia.id in visiveis
            and bool(set(respostas.get(dependencia.id, [])) & set(dependencia.valores))
        )
        valores = respostas.get(pergunta.id)
        if not visivel:
            if valores is not None:
                raise HTTPException(422, "Remova as respostas de campos que não se aplicam.")
            continue
        visiveis.add(pergunta.id)
        if valores is None:
            if pergunta.obrigatoria:
                raise HTTPException(422, f"Responda: {pergunta.texto}")
            continue
        if len(valores) != len(set(valores)) or (pergunta.tipo != "multipla" and len(valores) != 1):
            raise HTTPException(422, f"Quantidade de respostas inválida: {pergunta.texto}")
        opcoes = {item.valor: item.rotulo for item in pergunta.opcoes}
        if pergunta.tipo in ("escolha", "multipla"):
            if set(valores) - opcoes.keys():
                raise HTTPException(422, f"Selecione uma alternativa válida: {pergunta.texto}")
            if pergunta.tipo == "multipla" and len(valores) > 1 and set(valores) & {"nenhum", "desconhecido", "reservado"}:
                raise HTTPException(422, "Não combine alternativas exclusivas com outros procedimentos.")
        elif pergunta.tipo == "numero" and valores[0] != "desconhecido":
            try:
                numero = Decimal(valores[0])
            except InvalidOperation:
                raise HTTPException(422, "Informe um peso numérico válido.") from None
            if not numero.is_finite() or not 0 < numero <= Decimal("999.9"):
                raise HTTPException(422, "Informe um peso positivo de até 999,9 kg ou escolha não sei informar. Esse limite é técnico, não clínico.")
        elif pergunta.tipo == "data" and valores[0] != "desconhecido":
            try:
                dia = date.fromisoformat(valores[0])
            except ValueError:
                raise HTTPException(422, "Informe uma data válida ou escolha não sei informar.") from None
            if dia.isoformat() != valores[0] or dia > datetime.now(timezone.utc).date():
                raise HTTPException(422, "As datas de eventos passados não podem estar no futuro.")
        snapshot.append({
            "pergunta": pergunta.texto,
            "resposta": "; ".join(opcoes.get(valor, "Não sei informar" if valor == "desconhecido" else valor)
                                 for valor in sorted(valores)),
        })
    return snapshot


def metadados(envelope: dict[str, object] | None) -> MetadadosPreTriagem | None:
    return MetadadosPreTriagem.model_validate(envelope) if envelope is not None else None
