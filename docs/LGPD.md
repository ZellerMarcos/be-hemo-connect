# LGPD - Inventario e Governanca de Dados

Este documento consolida a base de conformidade do Requisito 4 para o backend.

## 1. Escopo

- Sistema: Hemo Connect Backend
- Repositorio: be-hemo-connect
- Modulos avaliados: cadastro, autenticacao, 2FA, recuperacao de senha e sessao

## 2. Inventario de dados pessoais coletados (4.1)

| Campo | Origem | Classificacao | Onde trafega | Onde persiste |
|---|---|---|---|---|
| nome | Cadastro de usuario | Dado pessoal comum | API /usuarios | tabela usuarios |
| cpf | Cadastro de usuario | Dado pessoal sensivel para identificacao civil | API /usuarios | tabela usuarios |
| email | Cadastro e autenticacao | Dado pessoal comum | API /usuarios, /auth/login, /auth/2fa/verify, /auth/forgot-password | tabela usuarios |
| senha | Cadastro e login/reset | Credencial | API /usuarios, /auth/login, /auth/reset-password | Nao persiste em texto puro |
| senha_hash | Processamento interno | Dado de seguranca | Nao exposto em resposta | tabela usuarios |
| perfil | Cadastro administrativo de acesso | Dado funcional de conta | API /usuarios | tabela usuarios |
| status | Cadastro administrativo de acesso | Dado funcional de conta | API /usuarios | tabela usuarios |
| hemocentro_id | Vinculo de operacao | Dado de vinculacao institucional | API /usuarios | tabela usuarios |
| coren_numero, coren_uf | Cadastro de enfermeiro | Identificacao profissional | /usuarios/solicitar-enfermagem, aprovacao administrativa e direitos do titular | tabela usuarios |
| aprovacao_pendente, aprovado_em, aprovado_por | Controle administrativo de acesso | Dados funcionais e de rastreabilidade | Fluxo de aprovacao | tabela usuarios |
| last_activity_at | Sessao | Dado tecnico de seguranca | Rotas protegidas | tabela usuarios |
| failed_login_attempts | Seguranca de login | Dado tecnico de seguranca | /auth/login | tabela usuarios |
| failed_login_window_started_at | Seguranca de login | Dado tecnico de seguranca | /auth/login | tabela usuarios |
| locked_until | Seguranca de login | Dado tecnico de seguranca | /auth/login | tabela usuarios |
| code_hash (2FA) | Gerado internamente | Dado de seguranca | /auth/login e /auth/2fa/verify | tabela two_factor_codes |
| token_hash (reset) | Gerado internamente | Dado de seguranca | /auth/forgot-password e /auth/reset-password | tabela password_reset_tokens |

## 3. Associacao dado -> finalidade (4.2)

| Campo | Finalidade principal | Base legal sugerida (validar com juridico) |
|---|---|---|
| nome, email, cpf | Identificacao e cadastro do titular | Execucao de contrato e/ou procedimentos preliminares |
| senha/senha_hash | Autenticacao segura | Seguranca da informacao e prevencao a fraude |
| perfil, status, hemocentro_id | Controle de acesso e operacao do sistema | Execucao de contrato e interesse legitimo operacional |
| COREN, UF e dados de aprovacao | Conferencia profissional e liberacao de acesso de enfermagem | Validar com juridico a base aplicavel ao cadastro profissional |
| dados de sessao e bloqueio | Prevencao de acesso indevido e forca bruta | Interesse legitimo em seguranca |
| token/codigo temporario | 2FA e recuperacao de conta | Seguranca da informacao |

## 4. Evidencia de minimizacao de dados (4.3)

O cadastro apresenta a política v1.2, que informa a coleta de COREN/UF e
a conferência administrativa, sem consulta automática ao conselho.
A finalidade `validacao_profissional` é registrada somente no cadastro
de enfermeiro. O número/UF constam na consulta e exportação do próprio titular
(incluindo PDF no frontend) e são limpos na anonimização, juntamente com
os campos de aprovação. Os eventos de auditoria não incluem o COREN.
Titulares pendentes, sem sessão, devem utilizar o suporte institucional
para solicitações de direitos, conforme o procedimento de identificação.

Diretrizes tecnicas adotadas:
- credenciais nao sao retornadas em respostas publicas;
- senha nao persiste em texto puro;
- 2FA e reset persistem somente hash de valores temporarios;
- token bruto nao aparece em logs;
- endpoints retornam payloads publicos sem `senha_hash`.

Lacunas para proxima fase:
- formalizar politica de retencao por tipo de dado;
- implementar revisao periodica de necessidade de cada campo;
- registrar base legal por operacao no nivel de processo.

## 5. Fluxo documentado de atendimento aos direitos (4.11)

### 5.1 Solicitar atendimento
- Canal inicial: suporte oficial da aplicacao.
- Identificacao minima: e-mail da conta e confirmacao de titularidade.

### 5.2 Triagem
- Classificar solicitacao: consulta, exportacao, exclusao, correcao, revogacao.
- Registrar protocolo e data/hora.

### 5.3 Execucao tecnica
- Consulta: extrair dados do titular sem dados de terceiros.
- Exportacao: gerar pacote estruturado.
- Exclusao: excluir ou anonimizar conforme obrigacao legal.
- Revogacao: desativar consentimentos aplicaveis.

### 5.4 Resposta ao titular
- Enviar retorno por canal autenticado.
- Registrar evidencias tecnicas da entrega.

### 5.5 Auditoria
- Guardar trilha de atendimento, responsavel, data e resultado.

## 6. Estado atual da implementacao

- consentimento explicito exigido no cadastro;
- politica de privacidade `v1.1` apresentada integralmente em modal antes do aceite;
- aceite liberado somente depois da rolagem completa do texto da politica;
- consentimentos persistidos por finalidade com versao de termo e timestamp;
- finalidades registradas no cadastro: cadastro, autenticacao, seguranca, doacao, triagem, atendimento, historico de doacoes, comunicacao, recuperacao de conta e melhoria da plataforma;
- revogacao de consentimento por finalidade disponivel em endpoint dedicado;
- consulta de dados do titular disponivel em `GET /privacy/me`;
- exportacao dos dados do titular disponivel em `GET /privacy/export`;
- exclusao com anonimização e desativacao da conta disponivel em `DELETE /privacy/me`.

## 7. Incremento da visão de enfermagem

- Data de nascimento, telefone e tipo sanguíneo são opcionais no cadastro,
  utilizados somente quando fornecidos e necessários ao atendimento.
- Agendamentos armazenam respostas institucionais de pré-triagem; avaliações
  armazenam observações, resultado e autoria.
- Consulta e exportação do titular incluem os novos campos e seus próprios
  atendimentos/respostas, sem identificadores de profissionais ou dados de terceiros.
- Sessões usam tokens opacos verificáveis pelo servidor. `X-User-Email` não
  identifica o titular autenticado.
- Acesso da enfermagem é restrito por perfil e hemocentro; CPF é mascarado na fila.
- Anonimização apaga os novos campos cadastrais e respostas de pré-triagem,
  revoga sessões e preserva vínculos operacionais.

Pendência de governança antes do uso com dados reais: formalizar retenção e base
legal de avaliações e auditoria, incluindo tratamento de dados pessoais em texto
livre. A anonimização do cadastro não apaga automaticamente observações clínicas
ou e-mails já presentes em registros imutáveis de auditoria.

Consulte [implantação da visão de enfermagem](VISAO_ENFERMEIRO.md).
