# Release do Projeto Hemo Connect

## Data da release
- 2026-08-29

## Visão geral
O projeto Hemo Connect está em evolução para apoiar o fluxo de autenticação, gestão de usuários, controle de sessão e cadastro de hemocentros, com uma estrutura dividida entre backend em FastAPI e frontend em React + Vite.

Nesta release, o foco principal foi consolidar o fluxo de acesso do usuário, o controle de timeout por inatividade e a criação de uma base funcional para a área logada do sistema.

---

## Status atual do projeto

### Backend
- API em FastAPI com rotas modulares para autenticação, usuários e hemocentros.
- Fluxo de login com validação de credenciais.
- Implementação de autenticação em duas etapas (2FA).
- Controle de sessão por inatividade com limite de 45 minutos.
- Expiração de sessão no backend com bloqueio de acesso às rotas protegidas.
- Logout funcional por sessão inválida ou expiração.
- Criação e atualização de usuários com regras de unicidade de CPF e e-mail.
- Proteção de rotas sensíveis por dependência de sessão ativa.

### Frontend
- Aplicação em React com Vite.
- Tela de login com autenticação e fluxo de 2FA.
- Tela de cadastro do usuário.
- Redirecionamento para login ao expirar a sessão.
- Exibição de mensagem de expiração da sessão:
  "Sua sessao expirou, realize novamente seu login"
- Tela básica pós-login com opções:
  - Marcar doacao
  - Meu Perfil
  - Histórico de Doacoes

---

## Funcionalidades implementadas

### 1. Autenticação e segurança
- Login com e-mail e senha.
- Verificação do código de 2FA.
- Controle de sessão por tempo de inatividade de 45 minutos.
- Bloqueio de acesso para usuários com sessão expirada.
- Logout do sistema.
- Proteção contra brute force: após 5 tentativas inválidas em uma janela de 15 minutos, a conta é bloqueada temporariamente por 1 hora.
- Mensagens de resposta do backend para alertar sobre tentativas restantes antes do bloqueio e sobre o período de lockout ativo.

### 2. Gestão de usuários
- Cadastro de usuários.
- Validação de dados de entrada.
- Regras para evitar CPF e e-mail duplicados.
- Atualização de dados do usuário.
- Exclusão de usuário.
- Exposição de informações relevantes em respostas da API.

### 3. Gestão de hemocentros
- Listagem de hemocentros.
- Consulta de hemocentro por identificador.
- Criação, edição e remoção de registros.

### 4. Experiência do usuário no frontend
- Fluxo completo de acesso ao sistema.
- Mensagens de feedback em login e validação do código.
- Redirecionamento para tela inicial após autenticação.
- Base de dashboard para área logada.

---

## Regras de negócio em vigor

### Sessão e timeout
- A sessão do usuário é considerada ativa enquanto houver atividade válida.
- Caso o usuário fique inativo por mais de 45 minutos, a aplicação invalida a sessão no backend.
- Rotas protegidas passam a rejeitar requisições com resposta de erro de autenticação.

### 2FA
- O login exige duas etapas.
- Após inserir e-mail e senha, o usuário precisa confirmar um código enviado para o e-mail cadastrado.

### Segurança
- Senhas são armazenadas em formato hash.
- Validações de unicidade e acesso impedem inconsistências de dados.
- Bloqueio temporário após múltiplas tentativas de login inválidas para reduzir risco de ataques de força bruta.
- Controle de janela de tentativas em 15 minutos e lockout de 1 hora para a conta afetada.

---

## Estrutura principal do projeto

### Backend
- app/
  - main.py
  - routes/
  - services/
  - schemas/
  - models/
  - database.py

### Frontend
- src/
  - App.tsx
  - pages/
  - services/
  - types/
  - index.css

---

## Estado atual

### Em andamento
- Refinamento do visual da área logada.
- Expansão dos módulos de navegação e ações do usuário.
- Aperfeiçoamento da experiência final para o fluxo de doação.

### Concluído até o momento
- Estrutura base do sistema funcional.
- Fluxo de login com 2FA.
- Sessão expirada por inatividade.
- Redirecionamento para login com mensagem de expiração.
- Dashboard inicial com ações principais.

---

## Observações
- O backend foi validado em ambiente de testes com SQLite para assegurar o comportamento do fluxo de autenticação e timeout.
- O frontend foi validado com build do projeto, confirmando que as alterações foram compiladas corretamente.

---

