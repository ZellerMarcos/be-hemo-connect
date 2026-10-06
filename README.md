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
- [Manual do enfermeiro](#manual-do-enfermeiro)
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

Execute os comandos a partir desta pasta (`be-hemo-connect`):

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

Antes de iniciar, crie um arquivo `.env` na raiz do backend a partir de
`.env.example`, caso ainda nao exista:

```powershell
Copy-Item -LiteralPath '.env.example' -Destination '.env'
```

Nao sobrescreva um `.env` existente. Edite o arquivo local e preencha
`DATABASE_URL` com a URL PostgreSQL do Supabase, utilizando o driver psycopg:

```env
DATABASE_URL=postgresql+psycopg://USUARIO:SENHA_CODIFICADA@HOST:5432/postgres?sslmode=require
```

Substitua os marcadores pelos dados da conexao. Caracteres especiais da senha
devem ser percent-encoded. Nunca compartilhe a senha nem versione o `.env`.
Configure tambem as variaveis do Brevo para utilizar login com 2FA.

O arquivo `.env.example` nao e carregado automaticamente. Sem `DATABASE_URL`
no `.env` ou no ambiente do processo, o backend interrompe a inicializacao com
`RuntimeError`. Variaveis ja definidas no processo prevalecem sobre o arquivo.
Reinicie o Uvicorn depois de alterar a configuracao.

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
| POST | `/usuarios/solicitar-enfermagem` | Solicita cadastro publico de enfermeiro com COREN e UF, sem liberar acesso. |
| GET | `/usuarios/aprovacoes/pendentes` | Administrador: lista solicitacoes de enfermagem paginadas. |
| POST | `/usuarios/aprovacoes/{id}/aprovar` | Administrador: confirma conferencia profissional e vincula a um hemocentro ativo. |
| PUT | `/usuarios/{id}` | Atualiza os dados permitidos do usuario. |
| DELETE | `/usuarios/{id}` | Exclui um usuario. |

### Cadastro de enfermeiro com COREN

No frontend, o titular escolhe **Doador(a)** ou **Enfermeiro(a)**. O doador
continua ativo após o cadastro. Para enfermeiros, número do COREN e UF são
obrigatórios; a solicitação fica `INATIVO`, com `aprovacao_pendente=true`
e sem hemocentro. O cadastro não permite enviar atributos de aprovação.

O administrador acessa `/users-approve`, confere externamente o registro,
a categoria, sua situação e a identidade, escolhe um hemocentro ativo e
confirma a conferência antes de aprovar. Só então o titular pode entrar com
senha e 2FA. O cadastro comum e o PUT não substituem a aprovação de uma
solicitação pendente.

**Não há validação profissional automática:** o sistema verifica apenas o
preenchimento/formato e a unicidade de número + UF. Os enfermeiros legados
não são desativados retroativamente.

Antes de publicar, aplique integralmente
[`sql/002_cadastro_enfermeiro_coren.sql`](sql/002_cadastro_enfermeiro_coren.sql)
no schema existente, em homologação primeiro. O script pressupõe a estrutura
base da aplicação; não cria `usuarios`, `hemocentros` ou `audit_logs`.
Não foi executado automaticamente no Supabase. Consulte o
[contrato de implantação](docs/VISAO_ENFERMEIRO.md).

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

No login, `verify_password()` valida a senha contra o hash armazenado.
O PUT de usuario nao altera a senha; a redefinicao utiliza token temporario.

## Autenticacao basica

`POST /auth/login` recebe e-mail e senha, localiza o usuario, verifica se ele
esta `ATIVO` e compara a senha com o hash Argon2id armazenado. E-mail inexistente,
e usuario `INATIVO` retornam `401`; senhas incorretas podem informar tentativas
restantes. O bloqueio temporario retorna `403` em novas tentativas.
O login inicia o 2FA e nunca retorna `senha` ou `senha_hash`.

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
`code`, retornando `authenticated=true`, o usuario real e um token Bearer
somente para um código válido.
O código não aparece em respostas ou logs, e o envio usa a API HTTPS do Brevo
por meio das variáveis `BREVO_API_KEY`, `MAIL_FROM` e `MAIL_FROM_NAME`. Esta etapa não cria
JWT. A sessão opaca é verificada no servidor, expira após 45 minutos de
inatividade e é revogada no logout. Todas as rotas protegidas exigem
`Authorization: Bearer <token>`; `X-User-Email` não autentica.

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

## Manual do enfermeiro

O [Manual do Enfermeiro](docs/MANUAL_ENFERMEIRO.md) orienta o acesso, a consulta
dos dados do doador e o fluxo de avaliacao e finalizacao da triagem.
Consulte [Visao do Enfermeiro](docs/VISAO_ENFERMEIRO.md) para migrations,
autorizacao, endpoints, implantacao e limites da base de atendimento.

Ordem dos scripts SQL no banco existente:

1. [000_create_hemocentros.sql](sql/000_create_hemocentros.sql)
2. [create_audit_logs.sql](sql/create_audit_logs.sql)
3. [001_visao_enfermeiro.sql](sql/001_visao_enfermeiro.sql)

Execute cada arquivo inteiro. O primeiro cria a tabela-base de hemocentros
somente se ausente, sem inserir registros. Se a tabela estiver em outro schema,
ajuste o `search_path` em vez de criar uma duplicata.

## Testes

A suite principal utiliza bancos SQLite isolados:

```powershell
$env:APP_ENV = "test"
python -m pytest tests -q --ignore=tests\test_health.py
```

O teste de saude acessa Uvicorn local na porta 8000 e e executado separadamente:

```powershell
python -m pytest tests\test_health.py -q
```

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

A base de atendimento tambem contempla agendamento, respostas de pre-triagem,
recepcao e visao do enfermeiro com historico de triagens. Disponibilidade de
vagas, coleta/doacao e visao medica permanecem fora deste incremento.