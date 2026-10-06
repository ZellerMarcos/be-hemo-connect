from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.hemocentro import Hemocentro
from app.models.usuario import Usuario
from app.schemas.usuario import AprovarEnfermeiroRequest, AprovacoesPendentesResponse
from app.security.audit import registrar_evento
from app.security.session import utcnow


def listar_pendentes(db: Session, pagina: int, tamanho: int) -> AprovacoesPendentesResponse:
    filters = (
        Usuario.perfil == "ENFERMEIRO", Usuario.status == "INATIVO",
        Usuario.aprovacao_pendente.is_(True),
    )
    total = db.scalar(select(func.count()).select_from(Usuario).where(*filters)) or 0
    itens = db.scalars(select(Usuario).where(*filters).order_by(Usuario.id)
                      .offset((pagina - 1) * tamanho).limit(tamanho)).all()
    return AprovacoesPendentesResponse(itens=itens, total=total, pagina=pagina, tamanho=tamanho)


def aprovar_enfermeiro(db: Session, administrador: Usuario, usuario_id: int,
                      data: AprovarEnfermeiroRequest) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuário não encontrado.")
    if usuario.perfil != "ENFERMEIRO" or not usuario.aprovacao_pendente or usuario.status != "INATIVO":
        raise HTTPException(409, "Usuário não possui solicitação de enfermagem pendente.")
    if not usuario.coren_numero or not usuario.coren_uf:
        raise HTTPException(409, "Solicitação sem COREN completo. Não é possível aprovar.")
    hemocentro = db.get(Hemocentro, data.hemocentro_id)
    if hemocentro is None or hemocentro.status != "ATIVO":
        raise HTTPException(422, "Selecione um hemocentro ativo.")
    changed = db.execute(update(Usuario).where(
        Usuario.id == usuario_id,
        Usuario.perfil == "ENFERMEIRO",
        Usuario.status == "INATIVO",
        Usuario.aprovacao_pendente.is_(True),
    ).values(
        status="ATIVO", hemocentro_id=data.hemocentro_id, aprovacao_pendente=False,
        aprovado_em=utcnow(), aprovado_por=administrador.id,
    ))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "A solicitação já foi aprovada ou alterada. Atualize a lista.")
    registrar_evento(db, "ENFERMEIRO_APROVADO", "sucesso",
                    user_id=administrador.id, alvo_usuario_id=usuario_id)
    db.refresh(usuario)
    return usuario
