import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse

from app.routes.health import router as health_router
from app.routes.auth import router as auth_router
from app.routes.hemocentros import router as hemocentros_router
from app.routes.usuarios import router as usuarios_router


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

# Mantém os eventos de negócio INFO visíveis no terminal junto dos avisos do Uvicorn.
logging.basicConfig(level=logging.INFO)
logging.getLogger("app").setLevel(logging.INFO)


app = FastAPI(
    title="Hemo Connect API",
    description="API para conectar doadores e hemocentros.",
)

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
cors_origins = list(dict.fromkeys([frontend_url, "http://localhost:5173"]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-User-Email"],
)

is_production = os.getenv("APP_ENV", "development").lower() == "production"


@app.middleware("http")
async def enforce_transport_security(request: Request, call_next):
    """Enforce HTTPS in production and attach baseline security headers."""
    if is_production:
        forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("host", "")
        is_local_host = host.startswith("localhost") or host.startswith("127.0.0.1")
        if forwarded_proto != "https" and not is_local_host:
            secure_url = request.url.replace(scheme="https")
            return RedirectResponse(url=str(secure_url), status_code=307)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(hemocentros_router)
app.include_router(usuarios_router)