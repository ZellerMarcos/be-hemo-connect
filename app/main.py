import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(hemocentros_router)
app.include_router(usuarios_router)