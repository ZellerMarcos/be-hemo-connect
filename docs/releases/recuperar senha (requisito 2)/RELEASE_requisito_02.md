# Release Backend do Projeto Hemo Connect

## Data da release
- 2026-09-05

## Visão geral
O backend do projeto Hemo Connect recebeu o fluxo de recuperação e redefinição de senha, permitindo que o usuário solicite um link por e-mail e atualize sua senha por meio de um token temporário e de uso único.

Nesta release, o foco principal foi implementar a recuperação segura de acesso, com geração de token aleatório, armazenamento protegido, validade limitada, invalidação de tokens anteriores e atualização da senha utilizando hash seguro.

---

## Status atual do projeto

### Backend
- API desenvolvida em FastAPI com rotas de autenticação centralizadas.
- Endpoint para solicitação de recuperação de senha.
- Endpoint para redefinição de senha com token.
- Geração de token temporário com alta aleatoriedade.
- Armazenamento somente do hash do token no banco de dados.
- Validade do token limitada a 15 minutos.
- Invalidação de tokens anteriores ainda não utilizados.
- Controle de uso único do token após a redefinição.
- Validação de usuário ativo antes da emissão e do uso do token.
- Envio do link de redefinição por e-mail.
- Atualização da senha utilizando hash Argon2id.
- Mensagens de erro para token inválido ou expirado.

---

## Funcionalidades implementadas

### 1. Solicitação de recuperação
- O endpoint `POST /auth/forgot-password` recebe o e-mail do usuário.
- O backend verifica se o usuário existe e está ativo.
- Para usuários válidos, o backend invalida solicitações pendentes anteriores.
- Um novo token aleatório é gerado para a solicitação atual.
- O hash do token é persistido na tabela de tokens de recuperação.
- O token possui validade de 15 minutos.
- O link de redefinição é enviado ao e-mail cadastrado.
- Em caso de falha no envio, o registro do token é removido para evitar tokens sem entrega confirmada.
- A resposta não revela se o e-mail está cadastrado, reduzindo risco de enumeração de usuários.

### 2. Validação e redefinição
- O endpoint `POST /auth/reset-password` recebe o token e a nova senha.
- O backend transforma o token recebido em hash para realizar a busca segura.
- Tokens já utilizados não podem ser reutilizados.
- Tokens expirados ou inexistentes são rejeitados.
- O usuário vinculado ao token precisa estar ativo.
- A senha precisa possuir pelo menos 8 caracteres.
- A nova senha é armazenada somente em formato de hash Argon2id.
- Após a atualização, o token é marcado como utilizado.

### 3. Segurança da operação
- O token bruto não é armazenado no banco de dados.
- A comparação do token utiliza comparação segura contra diferenças de tempo.
- Tokens anteriores são invalidados quando uma nova solicitação é realizada.
- O token expira automaticamente após 15 minutos.
- O token é consumido após uma redefinição concluída.
- A senha original nunca é registrada em texto puro.
- Falhas de envio de e-mail não deixam uma solicitação válida abandonada no banco.

---

## Regras de negócio em vigor

### Recuperação de senha
- Somente usuários ativos podem iniciar o processo de recuperação.
- A resposta da solicitação é neutra para não confirmar a existência do e-mail.
- Cada nova solicitação invalida tokens pendentes anteriores do mesmo usuário.
- O link enviado contém um token temporário para concluir a operação.

### Token de recuperação
- O token possui validade de 15 minutos.
- Apenas o hash do token é armazenado no banco.
- O token pode ser utilizado uma única vez.
- Token inexistente, expirado ou já utilizado gera erro de solicitação inválida.

### Nova senha
- A senha deve possuir no mínimo 8 caracteres.
- A senha é protegida com Argon2id antes de ser persistida.
- A redefinição concluída invalida o token utilizado.
- Após a alteração, o usuário deve realizar o login novamente com a nova senha.

---

## Endpoints disponibilizados

### Solicitar recuperação

`POST /auth/forgot-password`

Payload:

```json
{
  "email": "usuario@example.com"
}
```

Resposta:

```json
{
  "sent": true
}
```

### Redefinir senha

`POST /auth/reset-password`

Payload:

```json
{
  "token": "token-recebido-no-link",
  "senha": "NovaSenhaSegura123!"
}
```

Resposta:

```json
{
  "reset": true
}
```

---

## Estrutura principal do projeto

### Backend
- app/
  - routes/
    - auth.py
  - services/
    - auth.py
    - email.py
  - schemas/
    - auth.py
  - models/
    - password_reset_token.py
  - security/
    - password.py
  - database.py

---

## Fluxo da funcionalidade

1. O cliente envia o e-mail para `POST /auth/forgot-password`.
2. O backend verifica o usuário e invalida tokens pendentes anteriores.
3. O backend gera um novo token e armazena somente seu hash.
4. O link com o token é enviado ao e-mail do usuário.
5. O usuário envia o token e a nova senha para `POST /auth/reset-password`.
6. O backend valida existência, validade e uso do token.
7. A nova senha é transformada em hash Argon2id.
8. A senha é atualizada e o token é marcado como utilizado.
9. O usuário pode realizar um novo login com a senha atualizada.

---

## Estado atual

### Concluído até o momento
- Modelo de persistência dos tokens de recuperação.
- Geração segura de tokens temporários.
- Hash dos tokens antes do armazenamento.
- Solicitação de recuperação por e-mail.
- Invalidação de tokens pendentes anteriores.
- Validação de validade e uso único.
- Redefinição da senha com hash Argon2id.
- Tratamento de usuários inexistentes, inativos, tokens inválidos e tokens expirados.
- Documentação dos endpoints e das regras de negócio.

### Em andamento
- Configuração do endereço base do frontend por ambiente.
- Configuração do serviço SMTP para diferentes ambientes.
- Evolução de políticas adicionais de complexidade e histórico de senhas.
- Automatização das migrações da tabela `password_reset_tokens`.

---

## Observações
- A tabela `password_reset_tokens` deve existir no banco de dados utilizado pelo ambiente.
- As configurações de SMTP devem estar definidas para que os links sejam enviados por e-mail.
- O endereço do link de redefinição deve ser configurado por variável de ambiente em ambientes diferentes do desenvolvimento local.
- A validade, o uso único e a segurança do token são controlados pelo backend.

---
