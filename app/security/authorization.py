from fastapi import Depends, HTTPException

from app.models.usuario import Usuario
from app.routes.auth import require_active_session


def require_roles(*roles: str):
    def dependency(usuario: Usuario = Depends(require_active_session)) -> Usuario:
        if usuario.perfil not in roles:
            raise HTTPException(403, "Perfil sem permissão para esta operação.")
        return usuario
    return dependency


def require_hemocentro(usuario: Usuario) -> int:
    if usuario.hemocentro_id is None:
        raise HTTPException(403, "Profissional sem vínculo com um hemocentro.")
    return usuario.hemocentro_id
