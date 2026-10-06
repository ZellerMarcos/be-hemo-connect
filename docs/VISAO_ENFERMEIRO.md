# Visão do Enfermeiro — implantação e contrato

## Escopo implementado

O fluxo mínimo integrado é:

`DOADOR: agendamento + respostas → RECEPÇÃO: chegada → ENFERMEIRO: início →
avaliação → APTO / INAPTO / ENCAMINHADO_MEDICO → histórico de triagens`.

As telas são mantidas no repositório irmão `fe-hemo-connect`.
Não há registros fictícios nem avaliação clínica automática.

## Implantação

1. Faça backup e valide as migrations em um ambiente de homologação.
2. No PostgreSQL existente, confirme o schema e aplique
   [`000_create_hemocentros.sql`](../sql/000_create_hemocentros.sql). O script cria
   a tabela-base conforme o modelo existente, somente se estiver ausente,
   sem inserir dados ou substituir registros.
3. Aplique
   [`create_audit_logs.sql`](../sql/create_audit_logs.sql), caso o mecanismo de
   auditoria ainda não esteja instalado.
4. Aplique [`001_visao_enfermeiro.sql`](../sql/001_visao_enfermeiro.sql).
   Depois aplique [`002_cadastro_enfermeiro_coren.sql`](../sql/002_cadastro_enfermeiro_coren.sql)
   antes de publicar o cadastro e o painel de aprovação.
5. Publique backend e frontend juntos: clientes antigos que enviam
   `X-User-Email` deixam de autenticar e precisam efetuar um novo login.
6. Configure `DATABASE_URL`, `FRONTEND_URL`, `APP_ENV=production`, `BREVO_API_KEY`,
   `MAIL_FROM` e `MAIL_FROM_NAME`. O frontend utiliza `VITE_API_URL`.
7. Use uma conta administrativa já existente, autenticada após o 2FA, para
   aprovar solicitações de enfermeiros na tela `/users-approve`. A criação
   administrativa direta de profissionais em `POST /usuarios` continua
   disponível; novos enfermeiros também precisam de COREN e UF.
8. Vincule o enfermeiro ao hemocentro ativo durante a aprovação. Vincule
   recepcionistas ao `hemocentro_id` correspondente no cadastro administrativo.
9. Confirme o fluxo com doador, recepção e enfermeiro em homologação.

Se ocorrer `relation "hemocentros" does not exist`, verifique o banco/schema:

```sql
SELECT current_schema(), current_setting('search_path');
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name IN ('usuarios', 'hemocentros');
```

Execute cada arquivo SQL inteiro, incluindo `BEGIN` e `COMMIT`, e não apenas
o trecho selecionado no editor. Se uma execução deixou a transação abortada,
execute `ROLLBACK;` antes de tentar novamente. Se a tabela já existir em outro
schema, ajuste o `search_path` para o schema utilizado pela aplicação em vez de
duplicá-la. O script-base interrompe explicitamente nesse caso.

Não existe criação pública de contas administrativas. Se não houver uma conta
administrativa no banco, seu provisionamento inicial deve ser realizado pelo
operador autorizado, mantendo o hash Argon2id e o consentimento do titular.
As migrations não criam usuários, senhas ou hemocentros de demonstração.

As migrations são manuais e transacionais; a aplicação não cria as novas
tabelas no startup. Não foram aplicadas automaticamente ao banco remoto.

Os scripts anteriores citados nesta seção não estão presentes na pasta SQL
desta cópia do projeto. Se a estrutura base ainda não estiver instalada,
recupere esses scripts da versão de implantação antes de executar a migration
002. Ela apenas acrescenta campos e índices à tabela `usuarios` existente.

## Alterações de banco

| Entidade | Campos | Finalidade |
| --- | --- | --- |
| `hemocentros`, quando ausente | `id SERIAL`, `nome VARCHAR(255)`, `endereco VARCHAR(500)`, `telefone VARCHAR(30)`, `status hemocentro_status` | Pré-requisito já definido pelo modelo existente; não contém unidades fictícias. |
| `usuarios` | `data_nascimento DATE`, `telefone VARCHAR(30)`, `tipo_sanguineo VARCHAR(3)`, todos opcionais | Dados necessários ao atendimento, quando fornecidos. |
| `usuarios` | `coren_numero VARCHAR(20)`, `coren_uf VARCHAR(2)`, `aprovacao_pendente BOOLEAN DEFAULT FALSE`, `aprovado_em TIMESTAMP`, `aprovado_por` referenciando `usuarios` | Credencial informada, pendência e autoria da aprovação; unicidade de número + UF. |
| `auth_sessions` | Usuário, hash único do token, criação, atividade e revogação | Sessão verificável no servidor, independente por login. |
| `agendamentos` | Doador, hemocentro, data/hora UTC, status, respostas JSON, criação e recepção | Origem real da fila de atendimento. |
| `triagens` | Agendamento único, enfermeiro responsável, início, finalização, observações, resultado e versão | Avaliação com autoria e proteção contra sobrescrita. |

Agendamentos referenciam doador e hemocentro; triagens referenciam agendamento
e profissional. Não há entidade de doação realizada: o histórico corresponde
a **triagens finalizadas**, sem simular coleta ou doação.

## Autenticação e autorização

- `POST /auth/login` continua exigindo senha e enviando o 2FA.
- `POST /auth/2fa/verify` retorna `authenticated`, `nome`, `usuario`,
  `access_token` e `token_type=bearer`. O usuário contém os dados reais do perfil.
- O token opaco é aleatório; somente seu hash SHA-256 é persistido.
- Nas operações protegidas, envie `Authorization: Bearer <access_token>`.
- `GET /auth/me` permite restaurar e validar a identidade.
- A sessão expira após 45 minutos sem requisição autenticada válida.
- Logout revoga a sessão utilizada; redefinição de senha e anonimização revogam
  todas as sessões da conta.
- O frontend guarda o token em `sessionStorage`, não o envia em URLs e exige
  validação no backend para restaurar a sessão. Proteção contra XSS continua
  necessária; esconder uma tela nunca substitui autorização no servidor.
- Cadastro público permite doador ativo ou solicitação de enfermeiro inativo,
  sem vínculo institucional. O servidor define a pendência de aprovação;
  campos administrativos extras são rejeitados. Nenhum outro perfil possui
  cadastro público.
- Contas pendentes não autenticam, não validam 2FA, não recebem reset de senha
  nem utilizam sessão, mesmo se seu status for indevidamente alterado para ativo.
- Somente administradores listam e aprovam pendências. O PUT geral não libera
  essas contas. Criação administrativa de profissionais e demais mudanças
  de perfil/status/vínculo continuam exigindo administrador.
- Usuários não administrativos consultam e alteram somente sua própria conta.
- Apenas enfermeiros acessam as APIs de enfermagem, restritas ao hemocentro
  vinculado. Médicos, doadores, recepcionistas e administradores não realizam
  avaliações de enfermagem.
- Recepcionistas e responsáveis consultam a recepção da própria unidade.
  Administradores podem consultar a recepção de todas as unidades.
- Somente o enfermeiro que iniciou a triagem salva ou finaliza a avaliação.

## APIs

| Método | Rota | Perfil e finalidade |
| --- | --- | --- |
| POST | `/usuarios/solicitar-enfermagem` | Público: solicitação com COREN/UF e consentimento, inativa e sem hemocentro. |
| GET | `/usuarios/aprovacoes/pendentes` | Administrador: `itens`, `total`, `pagina`, `tamanho` (1–100); nome, e-mail, número e UF. |
| POST | `/usuarios/aprovacoes/{id}/aprovar` | Administrador: confirmação explícita e hemocentro ativo. |
| GET | `/triagens/indicadores` | Enfermeiro: contagens da unidade. |
| GET | `/triagens` | Enfermeiro: fila com busca, status, período e paginação. |
| GET | `/triagens/{id}` | Enfermeiro: dados necessários, respostas, histórico e avaliação. |
| POST | `/triagens/{id}/iniciar` | Enfermeiro: assumir atendimento pendente. |
| PUT | `/triagens/{id}` | Enfermeiro responsável: salvar observações sem finalizar. |
| POST | `/triagens/{id}/finalizar` | Enfermeiro responsável: observações e resultado. |
| POST | `/agendamentos` | Doador: registrar agendamento e respostas institucionais. |
| GET | `/agendamentos/me` | Doador: seus próprios agendamentos. |
| GET | `/historico/me` | Doador: suas próprias triagens finalizadas. |
| GET | `/recepcao/agendamentos` | Recepção autorizada: agendamentos aguardando chegada. |
| POST | `/recepcao/agendamentos/{id}/receber` | Recepção autorizada: confirmar chegada. |

### Conferência e aprovação de cadastro

Na solicitação pública, `perfil=ENFERMEIRO`, `status=INATIVO`,
`hemocentro_id=null`, `coren_numero` e `coren_uf` acompanham os dados e o
consentimento do cadastro. Número aceita 1–20 dígitos ASCII; esse limite é
de armazenamento, **não é uma regra de habilitação profissional**. Número e
UF são aparados; UF é convertida para maiúsculas e deve ser uma UF brasileira.
A combinação número + UF é única; conflito retorna `409`.

O administrador deve conferir por procedimentos oficiais da instituição
o registro, sua categoria/situação e a identidade. Não há integração com
serviço oficial do COREN. Após conferir, envia:

```json
{
  "hemocentro_id": 1,
  "conferencia_confirmada": true
}
```

O `{id}` desta aprovação é o **ID do usuário**, não o do atendimento.
A confirmação deve ser o booleano `true`, não número/string. Unidade ausente
ou inativa e confirmação inválida retornam `422`; aprovação repetida ou
concorrente retorna `409`. A atualização condicional libera somente uma vez,
registra administrador/data e gera auditoria na mesma transação.
Não há rejeição no painel nem notificação automática por e-mail.

### Rotas de atendimento

O `{id}` das rotas de enfermagem identifica o **agendamento/atendimento**.
Os status são `AGENDADO`, `AGUARDANDO_TRIAGEM`, `EM_TRIAGEM`, `APTO`, `INAPTO`
e `ENCAMINHADO_MEDICO`. Não foi criado `CONCLUIDO`, pois a conclusão já é
representada pelo resultado e por `finalizada_em`.

A fila aceita `busca` (nome ou dígitos de CPF), `status`, `inicio`, `fim`,
`pagina` e `tamanho` (até 100). O período usa datas UTC, com início e fim
inclusivos. A resposta contém `itens`, `total`, `pagina` e `tamanho`.
O CPF é mascarado na lista; no atendimento, é acessível ao enfermeiro autorizado.

Os indicadores abrangem todos os atendimentos da unidade e não seguem os
filtros da lista. `concluidas` soma todos os resultados finais, incluindo
`encaminhadas_medico`, que é também apresentada separadamente.

### Salvar avaliação

```json
{
  "observacoes": "Registro da avaliação conforme o protocolo institucional.",
  "versao": 1
}
```

### Finalizar

```json
{
  "observacoes": "Registro revisado da avaliação.",
  "versao": 2,
  "resultado": "ENCAMINHADO_MEDICO"
}
```

O campo `versao` deve corresponder à avaliação consultada. Cada gravação o
incrementa; uma versão desatualizada retorna `409`. Início e finalização
utilizam atualizações condicionais para impedir disputa pelo atendimento e
finalizações repetidas. Respostas de pré-triagem não são editáveis pelo enfermeiro.

## Auditoria e privacidade

Os eventos de agendamento, recepção, início, salvamento e resultado reutilizam
`audit_logs`. Metadados contêm apenas o identificador do atendimento; não
armazenam o questionário nem observações clínicas. No PostgreSQL, um bloqueio
transacional serializa o encadeamento dos hashes entre processos.

A exclusão de conta preserva vínculos de atendimento/autoria, anonimiza o
cadastro, apaga os novos campos pessoais e respostas de pré-triagem e revoga
sessões. Registros de avaliação e auditoria não são apagados automaticamente:
a instituição deve definir retenção, base legal e tratamento de texto livre
que possa conter dados pessoais antes do uso com dados reais.

## Limites explícitos desta base

- Não foi definido um questionário clínico oficial. A base armazena pares
  `pergunta`/`resposta` fornecidos pela instituição; não inventa perguntas ou
  interpretações.
- A avaliação contém observações e resultado. Pressão, frequência cardíaca,
  temperatura e peso não foram criados como campos clínicos estruturados:
  dependem de definição institucional.
- Agendamento registra uma data futura com fuso, combinada com a unidade;
  não implementa capacidade, disponibilidade, cancelamento ou remarcação.
- A recepção confirma a chegada; não implementa um módulo administrativo completo.
- Encaminhamento médico fica registrado e visível, mas a visão médica ainda
  não foi implementada.
- Triagens finalizadas não são reabertas ou editadas nesta entrega.
- Não há atribuição/substituição do enfermeiro responsável durante o atendimento.

## Validação

Os testes em `tests/test_triagens.py` cobrem fluxo completo dos três resultados,
autorização por perfil, isolamento entre unidades/doadores, filtros, paginação,
validação, concorrência no início, versão, autoria, auditoria e sessão.
Os testes em `tests/test_aprovacoes.py` cobrem cadastro com COREN/UF,
autoaprovação rejeitada, bloqueio de pendentes, permissões administrativas,
confirmação obrigatória, hemocentro ativo, unicidade, concorrência,
atomicidade com auditoria, login após aprovação, privacidade e contas legadas.

```powershell
$env:APP_ENV = "test"
python -m pytest tests -q --ignore=tests\test_health.py
```

No frontend:

```powershell
npm.cmd run build
npm.cmd run lint
```

O teste de saúde separado exige Uvicorn local. As migrations PostgreSQL e o
envio real de e-mail precisam de validação no ambiente de homologação.

### Resultados verificados nesta entrega

- **138 testes backend aprovados**, incluindo saúde por HTTP em servidor local
  isolado (`HEALTH_URL` permite selecionar a URL sem ocupar a porta padrão).
- **Build TypeScript/Vite aprovado**.
- **ESLint aprovado**.
- Cadastro/aprovação no navegador com SQLite sintético: solicitação inativa
  e sem hemocentro, login pendente bloqueado, login administrativo com 2FA,
  listagem do COREN/UF, somente unidades ativas, botão bloqueado sem conferência,
  aprovação e fila atualizada. Login com 2FA do enfermeiro aprovado direciona
  à enfermagem; o mesmo enfermeiro não acessa `/users-approve`.
- Privacidade do enfermeiro aprovado no navegador: COREN/UF e consentimento
  v1.2 apresentados; geração de PDF de 3.309 bytes, `application/pdf`,
  assinatura `%PDF-` e presença do COREN e número no conteúdo descomprimido.
- Navegador com dados sintéticos em SQLite: login com perfil real e 2FA,
  recepção, fila, início, gravação, persistência após recarga, finalização com
  encaminhamento médico, atualização de indicadores e estado vazio.
- Navegador: bloqueio do doador em acesso direto à área de enfermagem,
  agendamento, respostas institucionais e consulta LGPD.
- Exportação LGPD: geração no navegador de Blob `application/pdf` válido,
  com assinatura `%PDF-` e 2.118 bytes no cenário sintético, incluindo os
  atendimentos. O salvamento do arquivo pelo navegador integrado não foi
  confirmado pelo evento de download da ferramenta.
- Navegador: erro HTTP 503 sem exposição de detalhes internos, retentativa
  e painel responsivo sem overflow horizontal em largura de 390 px.
- Os três resultados, concorrência, autoria e isolamento foram verificados
  pelos testes de backend.

Avisos não bloqueantes: deprecações existentes do FastAPI/TestClient e
`datetime.utcnow`, bundle Vite acima de 500 kB e um alerta de dependência de
severidade alta informado pelo `npm ci`. O alerta não foi corrigido
automaticamente: exige análise própria, sem alterações de dependências
desvinculadas desta entrega.

## Inventário de arquivos

### Criados no backend

- [`app/models/auth_session.py`](../app/models/auth_session.py)
- [`app/models/triagem.py`](../app/models/triagem.py)
- [`app/routes/triagens.py`](../app/routes/triagens.py)
- [`app/schemas/triagem.py`](../app/schemas/triagem.py)
- [`app/security/authorization.py`](../app/security/authorization.py)
- [`app/security/session.py`](../app/security/session.py)
- [`app/services/triagem.py`](../app/services/triagem.py)
- [`sql/create_audit_logs.sql`](../sql/create_audit_logs.sql)
- [`sql/000_create_hemocentros.sql`](../sql/000_create_hemocentros.sql)
- [`sql/001_visao_enfermeiro.sql`](../sql/001_visao_enfermeiro.sql)
- [`tests/__init__.py`](../tests/__init__.py)
- [`tests/conftest.py`](../tests/conftest.py)
- [`tests/session_helpers.py`](../tests/session_helpers.py)
- [`tests/test_triagens.py`](../tests/test_triagens.py)
- Este documento: [`docs/VISAO_ENFERMEIRO.md`](VISAO_ENFERMEIRO.md).

### Alterados no backend

- [`README.md`](../README.md)
- [`app/database.py`](../app/database.py)
- [`app/main.py`](../app/main.py)
- [`app/models/__init__.py`](../app/models/__init__.py)
- [`app/models/usuario.py`](../app/models/usuario.py)
- [`app/routes/auth.py`](../app/routes/auth.py)
- [`app/routes/hemocentros.py`](../app/routes/hemocentros.py)
- [`app/routes/usuarios.py`](../app/routes/usuarios.py)
- [`app/schemas/auth.py`](../app/schemas/auth.py)
- [`app/schemas/lgpd.py`](../app/schemas/lgpd.py)
- [`app/schemas/usuario.py`](../app/schemas/usuario.py)
- [`app/security/audit.py`](../app/security/audit.py)
- [`app/services/auth.py`](../app/services/auth.py)
- [`app/services/privacidade.py`](../app/services/privacidade.py)
- [`app/services/usuario.py`](../app/services/usuario.py)
- [`docs/AUDITORIA_E_LOGS.md`](AUDITORIA_E_LOGS.md)
- [`docs/CHECKLIST.md`](CHECKLIST.md)
- [`docs/LGPD.md`](LGPD.md)
- [`docs/MANUAL_ENFERMEIRO.md`](MANUAL_ENFERMEIRO.md)
- [`docs/SECURITY.md`](SECURITY.md)
- [`tests/test_auth.py`](../tests/test_auth.py)
- [`tests/test_health.py`](../tests/test_health.py)
- [`tests/test_hemocentros.py`](../tests/test_hemocentros.py)
- [`tests/test_privacidade.py`](../tests/test_privacidade.py)
- [`tests/test_usuarios.py`](../tests/test_usuarios.py)

### Criados no frontend (`fe-hemo-connect`)

- `src/components/layout/AreaLogada.tsx`
- `src/pages/Agendamentos.tsx`
- `src/pages/Enfermagem.tsx`
- `src/pages/Recepcao.tsx`
- `src/pages/TriagemEnfermagem.tsx`
- `src/services/session.ts`
- `src/services/triagens.ts`
- `src/types/triagem.ts`
- `src/utils/triagemFormatters.ts`

### Alterados no frontend (`fe-hemo-connect`)

- `README.md`
- `src/App.tsx`
- `src/pages/Cadastro.tsx`
- `src/pages/MeuPerfil.tsx`
- `src/pages/Privacidade.tsx`
- `src/pages/TwoFactor.tsx`
- `src/routes.ts`
- `src/services/api.ts`
- `src/services/auth.ts`
- `src/services/privacidade.ts`
- `src/types/auth.ts`
- `src/types/privacidade.ts`
- `src/types/usuario.ts`
- `src/utils/privacyExportPdf.ts`
- `src/utils/privacyFormatters.ts`

Não foi criada uma camada de repositories paralela: o projeto já concentra
persistência nos services SQLAlchemy, padrão mantido nesta entrega.
