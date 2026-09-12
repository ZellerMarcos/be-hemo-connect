import secrets
import logging
from datetime import datetime, timezone

from sqlalchemy import inspect, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.database import DB_SCHEMA
from app.models.consentimento import Consentimento
from app.models.password_reset_token import PasswordResetToken
from app.models.two_factor_code import TwoFactorCode
from app.models.usuario import Usuario
from app.security.password import hash_password


BASE_LEGAL_PADRAO = "Execucao de contrato e seguranca da informacao"
logger = logging.getLogger(__name__)


def _missing_consent_table(error: ProgrammingError) -> bool:
    message = str(error).lower()
    return "consentimentos" in message and "does not exist" in message


def _consent_table_exists(db: Session) -> bool:
    return inspect(db.bind).has_table("consentimentos", schema=DB_SCHEMA)


def registrar_consentimentos_iniciais(
    db: Session,
    usuario_id: int,
    finalidades: list[str],
    versao_termo: str,
    base_legal: str = BASE_LEGAL_PADRAO,
) -> None:
    # Persiste um registro de consentimento por finalidade no momento do cadastro.
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    finalidades_limpas = sorted({item.strip() for item in finalidades if item.strip()})
    for finalidade in finalidades_limpas:
        db.add(
            Consentimento(
                usuario_id=usuario_id,
                finalidade=finalidade,
                versao_termo=versao_termo,
                base_legal=base_legal,
                concedido=True,
                concedido_em=agora,
                revogado_em=None,
            )
        )


def listar_consentimentos(db: Session, usuario_id: int) -> list[Consentimento]:
    # Retorna o historico do titular, priorizando finalidade e ordem temporal mais recente.
    if not _consent_table_exists(db):
        logger.warning(
            "Tabela consentimentos ausente ao listar consentimentos | usuario_id=%s",
            usuario_id,
        )
        return []

    try:
        return list(
            db.scalars(
                select(Consentimento)
                .where(Consentimento.usuario_id == usuario_id)
                .order_by(Consentimento.finalidade.asc(), Consentimento.concedido_em.desc())
            ).all()
        )
    except ProgrammingError as error:
        if _missing_consent_table(error):
            db.rollback()
            logger.warning(
                "Tabela consentimentos ausente ao listar consentimentos | usuario_id=%s",
                usuario_id,
            )
            return []
        raise


def revogar_consentimento(db: Session, usuario_id: int, finalidade: str) -> Consentimento:
    # Marca o ultimo consentimento ativo como revogado sem remover o historico.
    if not _consent_table_exists(db):
        raise ValueError("Estrutura de consentimento indisponivel no banco de dados.")

    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        consentimento = db.scalar(
            select(Consentimento)
            .where(
                Consentimento.usuario_id == usuario_id,
                Consentimento.finalidade == finalidade,
                Consentimento.concedido.is_(True),
                Consentimento.revogado_em.is_(None),
            )
            .order_by(Consentimento.concedido_em.desc())
        )
    except ProgrammingError as error:
        if _missing_consent_table(error):
            db.rollback()
            raise ValueError("Estrutura de consentimento indisponivel no banco de dados.") from error
        raise
    if consentimento is None:
        raise ValueError("Consentimento ativo nao encontrado para a finalidade informada.")

    consentimento.concedido = False
    consentimento.revogado_em = agora
    db.commit()
    db.refresh(consentimento)
    return consentimento


def montar_dados_titular(db: Session, usuario: Usuario) -> dict[str, object]:
    # Monta o payload consolidado para consulta e exportacao de dados do titular.
    consentimentos = listar_consentimentos(db, usuario.id)
    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "cpf": usuario.cpf,
        "email": usuario.email,
        "perfil": usuario.perfil,
        "status": usuario.status,
        "hemocentro_id": usuario.hemocentro_id,
        "consentimentos": consentimentos,
    }


def excluir_dados_titular(db: Session, usuario: Usuario) -> None:
    # Aplica anonimizaçao dos dados pessoais e invalida artefatos ativos de autenticacao.
    usuario = db.merge(usuario)
    consent_table_exists = _consent_table_exists(db)
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    suffix = f"{usuario.id}_{int(agora.timestamp())}"

    usuario.nome = "Titular removido"
    usuario.cpf = f"{usuario.id:011d}"
    usuario.email = f"deleted_{suffix}@example.invalid"
    usuario.senha_hash = hash_password(secrets.token_urlsafe(32))
    usuario.status = "INATIVO"
    usuario.last_activity_at = None
    usuario.failed_login_attempts = 0
    usuario.failed_login_window_started_at = None
    usuario.locked_until = None

    codigos_ativos = db.scalars(
        select(TwoFactorCode).where(
            TwoFactorCode.usuario_id == usuario.id,
            TwoFactorCode.used_at.is_(None),
        )
    ).all()
    for code in codigos_ativos:
        code.used_at = agora

    tokens_ativos = db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.usuario_id == usuario.id,
            PasswordResetToken.used_at.is_(None),
        )
    ).all()
    for token in tokens_ativos:
        token.used_at = agora

    if consent_table_exists:
        consentimentos_ativos = db.scalars(
            select(Consentimento).where(
                Consentimento.usuario_id == usuario.id,
                Consentimento.concedido.is_(True),
                Consentimento.revogado_em.is_(None),
            )
        ).all()
        for consentimento in consentimentos_ativos:
            consentimento.concedido = False
            consentimento.revogado_em = agora
    else:
        logger.warning(
            "Tabela consentimentos ausente ao excluir dados do titular | usuario_id=%s",
            usuario.id,
        )

    db.commit()
