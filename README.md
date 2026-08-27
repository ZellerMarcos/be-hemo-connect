# Hemo Connect - Backend

Backend do Hemo Connect, uma plataforma para facilitar o agendamento de doacoes,
aproximar doadores dos hemocentros e incentivar uma frequencia maior de doacoes.
Nesta etapa, fornece uma API simples para verificar se o servico esta funcionando.

## Tecnologias

- Python 3.12 ou superior
- FastAPI
- Pydantic
- Uvicorn

## Pre-requisitos

- Python instalado e disponivel pelo comando `py` ou `python`.
- PowerShell, Bash ou outro terminal compativel.

## Instalacao

Execute os comandos a partir desta pasta (`be-lib-tech`):

```powershell
py -3 -m venv .venv
./.venv/Scripts/Activate.ps1
py -m pip install -r requirements.txt
```

No Linux ou macOS, a ativacao do ambiente e feita com:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

O ambiente virtual e local e esta incluido no `.gitignore`.

## Execucao

Com o ambiente virtual ativado:

```powershell
python -m uvicorn app.main:app --reload
```

Tambem e possivel executar usando diretamente o Python do ambiente virtual:

```powershell
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

O servidor fica disponivel em `http://127.0.0.1:8000`.

## Endpoints de hemocentros

| Metodo | Rota | Finalidade |
| --- | --- | --- |
| GET | `/hemocentros` | Lista os hemocentros. |
| GET | `/hemocentros/{id}` | Busca um hemocentro pelo ID. |
| POST | `/hemocentros` | Cria um hemocentro. |
| PUT | `/hemocentros/{id}` | Atualiza um hemocentro. |
| DELETE | `/hemocentros/{id}` | Exclui um hemocentro. |

Os campos obrigatorios sao `nome`, `endereco`, `telefone` e `status`. O campo
`status` aceita somente `ATIVO` ou `INATIVO`.

## Testes

O teste atual verifica o endpoint de saude por HTTP. Como ele acessa o servidor
local, inicie o Uvicorn em um terminal e execute o teste em outro:

```powershell
python -m unittest discover -s tests
```

Use `py -m unittest discover -s tests` caso o comando `python` nao esteja disponivel.

## Estrutura

```text
be-lib-tech/
|-- app/
|   |-- main.py                 # Cria a aplicacao FastAPI
|   |-- routes/                 # Rotas HTTP
|   |-- schemas/                # Modelos de resposta da API
|-- tests/                      # Testes automatizados
|-- requirements.txt            # Dependencias Python
|-- .gitignore                  # Arquivos locais ignorados
```

## Escopo atual

Ainda nao fazem parte desta etapa o banco MySQL, o ORM SQLAlchemy, autenticacao,
gerenciamento de usuarios, agendamento de doacoes e integracao com hemocentros.
Essas funcionalidades serao adicionadas separadamente, de forma incremental.