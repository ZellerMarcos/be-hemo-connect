from fastapi import APIRouter

from app.schemas.health import HealthResponse


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    # Endpoint de verificação simples para confirmar que a API está no ar e pronta para receber requisições.
    return HealthResponse(status="ok")