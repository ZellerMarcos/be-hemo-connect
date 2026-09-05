import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.health import router as health_router
from app.routes.auth import router as auth_router
from app.routes.hemocentros import router as hemocentros_router
from app.routes.usuarios import router as usuarios_router


# Mantém os eventos de negócio INFO visíveis no terminal junto dos avisos do Uvicorn.
logging.basicConfig(level=logging.INFO)
logging.getLogger("app").setLevel(logging.INFO)


app = FastAPI(
    title="Hemo Connect API",
    description="API para conectar doadores e hemocentros.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(hemocentros_router)
app.include_router(usuarios_router)