# Checklist do Projeto — Hemo Connect Backend

Este checklist organiza os requisitos de segurança implementados no backend do projeto Hemo Connect e facilita a conferência do que foi desenvolvido, documentado e testado.

## 1. Autenticação e Gestão de Credenciais

| Requisito | Implementação | Status |
|---|---|---|
| 1.1 — Hash seguro de senhas | Utilização do Argon2id para proteger as senhas antes do armazenamento | Concluído |
| 1.2 — Parâmetros de custo | Configuração de memória, tempo e threads do `PasswordHasher` | Concluído |
| 1.3 — Salt único | Salt gerado automaticamente pelo Argon2id a cada hash | Concluído |
| 1.4 — Armazenamento seguro | Persistência somente do hash da senha, sem texto puro | Concluído |
| 1.5 — Autenticação em dois fatores | Segundo fator por código temporário enviado por e-mail | Concluído |
| 1.6 — Validação do 2FA | Código validado quanto ao formato, validade, hash e expiração | Concluído |
| 1.7 — Fluxo de autenticação | Login, emissão do 2FA, confirmação, sessão e logout | Concluído |
| 1.8 — Duração da sessão | Controle de 45 minutos sem atividade válida | Concluído |
| 1.9 — Invalidação da sessão | `last_activity_at` limpo durante o logout | Concluído |
| 1.10 — Proteção contra força bruta | 5 tentativas inválidas em 15 minutos bloqueiam a conta por 1 hora | Concluído |
| 1.11 — Feedback de segurança | API informa tentativas restantes e situação de bloqueio | Concluído |
| 1.12 — Rotas protegidas | Dependência `require_active_session` valida usuário e inatividade | Concluído |
| 1.13 — Justificativas técnicas | Regras de autenticação descritas nas releases do requisito 1 | Concluído |

---

## 2. Recuperação de Senha

| Requisito | Implementação | Status |
|---|---|---|
| 2.1 — Funcionalidade implementada | Endpoints `POST /auth/forgot-password` e `POST /auth/reset-password` | Concluído |
| 2.2 — Token criptograficamente seguro | Token aleatório gerado com `secrets.token_urlsafe` | Concluído |
| 2.3 — Armazenamento protegido | Hash SHA-256 do token armazenado na tabela `password_reset_tokens` | Concluído |
| 2.4 — Token com tempo de expiração | Token válido por 15 minutos | Concluído |
| 2.5 — Token invalidado após uso | Token marcado com `used_at` após redefinição | Concluído |
| 2.6 — Invalidação de solicitação anterior | Tokens pendentes anteriores são invalidados ao gerar um novo | Concluído |
| 2.7 — Falha correta para token inválido ou expirado | API rejeita o token e não altera a senha | Concluído |
| 2.8 — Usuário ativo | Emissão e uso do token exigem usuário ativo | Concluído |
| 2.9 — Atualização segura da senha | Nova senha armazenada com hash Argon2id | Concluído |
| 2.10 — Envio do link | Link temporário encaminhado pelo serviço de e-mail | Concluído |
| 2.11 — Privacidade da solicitação | Resposta neutra não revela se o e-mail está cadastrado | Concluído |
| 2.12 — Registro da solicitação | Log `Usuário solicitou uma redefinição de senha` com status da solicitação | Concluído |
| 2.13 — Registro do envio | Log `Token enviado` com status do envio do link | Concluído |
| 2.14 — Registro do resultado | Logs `Reset bem sucedido` ou `Reset de senha ou pedido mal sucedido`, sem expor token ou senha | Concluído |
| 2.15 — Justificativas técnicas | Regras de recuperação descritas na release do requisito 2 | Concluído |

---

## 3. Funcionalidades verificadas

### Cadastro e login

- [x] Cadastro de usuários
- [x] Hash da senha no cadastro
- [x] Validação das credenciais no login
- [x] Geração do código de 2FA
- [x] Validação do código de 2FA
- [x] Registro da atividade após autenticação
- [x] Logout e limpeza da atividade da sessão

### Proteção das senhas

- [x] Utilização do Argon2id
- [x] Salt automático
- [x] Armazenamento do hash no banco de dados
- [x] Senha não armazenada em texto puro

### Sessões e rotas protegidas

- [x] Controle de atividade pelo campo `last_activity_at`
- [x] Expiração após 45 minutos de inatividade
- [x] Rejeição de requisições sem sessão válida
- [x] Renovação da atividade em requisições protegidas
- [x] Invalidação da sessão durante o logout

### Proteção contra tentativas excessivas

- [x] Contagem de falhas por usuário
- [x] Janela de 15 minutos
- [x] Limite de 5 tentativas inválidas
- [x] Bloqueio temporário de 1 hora
- [x] Mensagem com tentativas restantes
- [x] Limpeza do bloqueio após o prazo
- [x] Reset do contador após login válido

### Recuperação de senha

- [x] Solicitação de link por e-mail
- [x] Geração de token aleatório
- [x] Armazenamento somente do hash do token
- [x] Validade de 15 minutos
- [x] Invalidação após uso
- [x] Invalidação de tokens anteriores
- [x] Tratamento de token inválido ou expirado
- [x] Atualização da senha com Argon2id
- [x] Resposta neutra para e-mail não cadastrado

---

## 4. Evidências

Os testes automatizados do backend estão organizados em:

```text
tests/
```

Principais evidências automatizadas:

- `tests/test_auth.py` — login, 2FA, expiração de código, sessão e proteção de credenciais;
- `tests/test_auth.py` — bloqueio após 5 tentativas inválidas;
- `tests/test_auth.py` — expiração da sessão após 45 minutos de inatividade;
- `tests/test_health.py` — verificação de disponibilidade da API.

As evidências visuais ou capturas de ambiente devem ser adicionadas em `docs/evidences/` quando forem produzidas.

---

## 5. Documentação

A documentação detalhada das entregas está disponível em:

```text
docs/releases/autenticacao (requisito 1)/RELEASE_requisito_01.md
docs/releases/recuperar senha (requisito 2)/RELEASE_requisito_02.md
```

Esses arquivos descrevem o funcionamento, as regras de negócio, os endpoints, as decisões técnicas e as observações de configuração.

---

## 6. Situação atual

**Requisito 1 — Autenticação e Gestão de Credenciais: CONCLUÍDO**

**Requisito 2 — Recuperação de Senha: CONCLUÍDO**

O código-fonte, os testes e a documentação referentes aos requisitos estão organizados no repositório do backend.

> Para execução em SQL Server, as colunas de sessão, bloqueio e a tabela de tokens devem existir no banco utilizado pelo ambiente.
