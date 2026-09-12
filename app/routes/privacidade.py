from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.routes.auth import require_active_session
from app.schemas.lgpd import (
    ExclusaoTitularResponse,
    ExportacaoTitularResponse,
    RevogarConsentimentoRequest,
    RevogarConsentimentoResponse,
    TitularDadosResponse,
)
from app.services.privacidade import (
    excluir_dados_titular,
    montar_dados_titular,
    revogar_consentimento,
)


# Expõe os endpoints de direitos do titular para consulta, exportacao e gerenciamento de consentimento.
router = APIRouter(prefix="/privacy", tags=["Privacidade"])


@router.get("/me", response_model=TitularDadosResponse)
def get_me(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_active_session),
):
    # Retorna os dados do proprio titular autenticado, sem depender de ID em URL.
    return TitularDadosResponse.model_validate(montar_dados_titular(db, usuario))


@router.get("/export", response_model=ExportacaoTitularResponse)
def export_my_data(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_active_session),
):
    # Entrega um snapshot estruturado para portabilidade de dados do titular.
    return ExportacaoTitularResponse(
        titular=TitularDadosResponse.model_validate(montar_dados_titular(db, usuario)),
        exportado_em=datetime.now(timezone.utc).replace(tzinfo=None),
    )


@router.post("/consent/revoke", response_model=RevogarConsentimentoResponse)
def revoke_consent(
    data: RevogarConsentimentoRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_active_session),
):
    # Revoga o consentimento de uma finalidade especifica para o titular autenticado.
    try:
        consentimento = revogar_consentimento(db, usuario.id, data.finalidade)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return RevogarConsentimentoResponse(
        revogado=True,
        finalidade=consentimento.finalidade,
        revogado_em=consentimento.revogado_em,
    )


@router.delete("/me", response_model=ExclusaoTitularResponse)
def delete_my_data(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_active_session),
):
    # Executa exclusao logica com anonimizaçao para reduzir risco de reidentificacao.
    excluir_dados_titular(db, usuario)
    return ExclusaoTitularResponse(
        excluido=True,
        mensagem="Dados pessoais anonimizados e conta desativada com sucesso.",
    )
