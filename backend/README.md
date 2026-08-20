# lib.tech-backend

Backend do Sistema de Biblioteca Inteligente e Inclusiva.

## Tecnologias

- Python
- FastAPI
- Pydantic
- Uvicorn

## Instalação

Crie e ative o ambiente virtual:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

Instale as dependências:

```powershell
pip install -r requirements.txt
```

## Execução

```powershell
uvicorn app.main:app --reload
```

## Health Check

`GET /health`

## Documentação

- `/docs`
- `/redoc`