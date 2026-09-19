# Hemo Connect - Backend

Backend do Hemo Connect, uma plataforma para facilitar o agendamento de doacoes,
aproximar doadores dos hemocentros e incentivar uma frequencia maior de doacoes.
Nesta etapa, fornece uma API simples para verificar se o servico esta funcionando.

## Sumario

- [Tecnologias](#tecnologias)
- [Pre-requisitos](#pre-requisitos)
- [Instalacao](#instalacao)
- [Execucao](#execucao)
- [Endpoints de hemocentros](#endpoints-de-hemocentros)
- [Endpoints de usuarios](#endpoints-de-usuarios)
- [Fluxo da senha](#fluxo-da-senha)
- [Autenticacao basica](#autenticacao-basica)
- [2FA por e-mail](#2fa-por-e-mail)
- [Envio de e-mails](#envio-de-e-mails)
- [Comunicacao segura e criptografia](#comunicacao-segura-e-criptografia)
- [LGPD e privacidade](#lgpd-e-privacidade)
- [Auditoria e logs](#auditoria-e-logs)
- [Testes](#testes)
- [Estrutura](#estrutura)
- [Escopo atual](#escopo-atual)

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

## Endpoints de usuarios

| Metodo | Rota | Finalidade |
| --- | --- | --- |
| GET | `/usuarios` | Lista os usuarios cadastrados. |
| GET | `/usuarios/{id}` | Busca um usuario pelo ID. |
| POST | `/usuarios` | Cadastra um usuario recebendo uma senha e armazenando seu hash. |
| PUT | `/usuarios/{id}` | Atualiza os dados permitidos do usuario. |
| DELETE | `/usuarios/{id}` | Exclui um usuario. |

### Fluxo da senha

O POST recebe `senha`, aplica Argon2id e armazena somente o resultado em
`senha_hash` no PostgreSQL do Supabase:

`senha` -> `Argon2id` -> `hash` -> `PostgreSQL/Supabase`

A senha original nunca e armazenada ou retornada pela API. O salt e gerado
automaticamente pela biblioteca, de forma criptograficamente segura e unica em
cada hash. Os parametros de custo centralizados no modulo de seguranca usam
`time_cost=2`, `memory_cost=65536 KiB`, `parallelism=2`, `hash_len=32` e
`salt_len=16`, equilibrando protecao e tempo adequado para desenvolvimento
local e um projeto universitario.

Em uma etapa futura, a senha informada podera ser validada com
`verify_password()` contra o hash armazenado. O PUT atual nao altera a senha.

## Autenticacao basica

`POST /auth/login` recebe e-mail e senha, localiza o usuario, verifica se ele
esta `ATIVO` e compara a senha com o hash Argon2id armazenado. E-mail inexistente,
senha incorreta e usuario `INATIVO` retornam a mesma resposta `401` generica.
O retorno contem somente dados basicos do usuario; nunca inclui `senha` ou
`senha_hash`.

## 2FA por e-mail

O segundo fator usa um codigo aleatorio de seis digitos enviado ao e-mail
cadastrado depois que o e-mail e a senha sao validados com Argon2id. O codigo
vale por cinco minutos, e apenas o hash dele e armazenado na tabela
`public.two_factor_codes`. Depois de validado, o codigo e marcado como utilizado e
nao pode ser reutilizado. Um novo login invalida o codigo pendente anterior.

Fluxo:

`Login` -> `E-mail + senha` -> `Argon2id` -> `Senha correta` ->
`Geração do código` -> `Envio por e-mail` -> `Código informado` ->
`Validação` -> `2FA aprovado`

O endpoint `POST /auth/login` retorna `{"requires_2fa": true}` quando o código
foi gerado e enviado. O endpoint `POST /auth/2fa/verify` recebe `email` e
`code`, retornando `{"authenticated": true}` somente para um código válido.
O código não aparece em respostas ou logs, e o envio usa a API HTTPS do Brevo
por meio das variáveis `BREVO_API_KEY`, `MAIL_FROM` e `MAIL_FROM_NAME`. Esta etapa não cria
sessão, JWT, logout ou autorização.

## Envio de e-mails

O Hemo Connect utiliza o Brevo como provedor de e-mail pela API transacional
HTTPS. O envio ocorre sem SMTP, porque o Render Free não
permite tráfego SMTP de saída nas portas 25, 465 e 587.

Configure localmente ou no serviço do Render:

```env
BREVO_API_KEY=xkeysib-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MAIL_FROM=seu-remetente@seu-dominio.com
MAIL_FROM_NAME=Hemo Connect
```

No Render, configure essas variáveis no painel do serviço. O arquivo `.env`
local não é utilizado pelo ambiente de produção. Para usar um remetente próprio,
o endereço ou domínio precisa estar verificado e autorizado no Brevo.

## Comunicacao segura e criptografia

O requisito 3 foi consolidado com foco em transporte seguro e protecao de
credenciais:

- conexao com Supabase exige TLS por `sslmode=require`;
- envio de e-mail usa API HTTPS do Brevo;
- middleware HTTP aplica cabecalhos de seguranca e, em producao
	(`APP_ENV=production`), redireciona requisicoes inseguras para HTTPS;
- senhas usam Argon2id e tokens temporarios usam hash SHA-256.

Consulte:

- `docs/SECURITY.md`
- `docs/releases/criptografia (requisito 3)/RELEASE_requisito_03.md`

## LGPD e privacidade

Os endpoints de privacidade permitem que o proprio titular consulte, exporte,
revogue consentimentos e solicite exclusao/anonimizacao de dados:

| Metodo | Rota | Finalidade |
| --- | --- | --- |
| GET | `/privacy/me` | Consulta dados do titular autenticado. |
| GET | `/privacy/export` | Exporta dados do titular para portabilidade. |
| POST | `/privacy/consent/revoke` | Revoga consentimento por finalidade. |
| DELETE | `/privacy/me` | Anonimiza dados pessoais e desativa a conta. |

Detalhes tecnicos e evidencias:

- `docs/LGPD.md`
- `docs/releases/conformidade lgpd (requisito 4)/RELEASE_requisito_04.md`

## Auditoria e logs

O backend registra eventos estruturados de autenticacao, 2FA, sessao, logout e
redefinicao de senha. Os registros nao incluem senhas, hashes, codigos 2FA,
tokens, URLs de reset ou segredos de ambiente. A aplicacao apenas emite novos
eventos e persistidos na tabela `audit_logs`, com hash SHA-256 encadeado,
timestamp, usuario, motivo e metadados operacionais seguros. O arquivo
`sql/create_audit_logs.sql` deve ser executado manualmente no PostgreSQL antes
do deploy; a aplicacao nao cria a tabela automaticamente.

Consulte:

- `docs/AUDITORIA_E_LOGS.md`
- `docs/releases/auditoria e logs (requisito 5)/RELEASE_requisito_05.md`

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

O backend ja contempla:

- API FastAPI com rotas de saude, autenticacao, usuarios, hemocentros e privacidade;
- persistencia com SQLAlchemy;
- autenticacao com senha hash, fluxo 2FA por e-mail e reset de senha;
- controles de seguranca de transporte e requisitos de criptografia/LGPD.

Itens como jornada completa de agendamento e historico detalhado de doacoes
podem evoluir em incrementos futuros.