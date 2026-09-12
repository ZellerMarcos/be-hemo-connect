# Seguranca - Criptografia e Comunicacao Segura

Este documento consolida a estrategia de seguranca para o requisito 3.

## 1. Escopo

O backend e responsavel por:
- proteger credenciais;
- proteger tokens temporarios;
- exigir transporte seguro em producao;
- centralizar integracoes com banco e envio de e-mail por HTTPS/TLS.

## 2. Comunicacao segura (3.1, 3.2, 3.3)

- Frontend -> Backend: HTTPS em producao, com bloqueio de URL insegura no frontend.
- Backend -> Supabase PostgreSQL: conexao com TLS obrigatorio via `sslmode=require`.
- Backend -> Resend: chamada HTTPS pelo SDK oficial.
- Middleware no backend adiciona cabecalhos de seguranca e redireciona para HTTPS em producao.

Cabecalhos enviados pelo backend:
- `Strict-Transport-Security` (somente em producao)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`

## 3. Dados sensiveis em repouso (3.4)

- Senhas: hash Argon2id.
- Codigo 2FA: hash SHA-256.
- Token de reset: hash SHA-256 + comparacao em tempo constante.

Observacao:
- Este projeto nao persiste senha em texto puro.
- Para PII (ex.: nome, email), a protecao principal atual e controle de acesso + banco gerenciado. Criptografia de coluna pode ser avaliada em fase futura caso exigencia regulatoria determine.

## 4. Escolhas criptograficas (3.5)

- Argon2id para senha:
  - motivo: algoritmo memory-hard recomendado para resistencia a forca bruta em hardware paralelo.
- SHA-256 para token/codigo temporario:
  - motivo: necessidade de irreversibilidade e comparacao, sem recuperar valor original.
- `hmac.compare_digest` para comparacao:
  - motivo: reduzir variacao temporal observavel.

## 5. Protecao de chaves e segredos (3.6)

- Segredos nao sao versionados no repositorio.
- Variaveis sensiveis sao fornecidas por ambiente (Render/Supabase/Resend).
- Arquivos locais de ambiente ficam fora do controle de versao.

Politica minima de rotacao:
1. Gerar novo segredo no provedor.
2. Atualizar variavel no ambiente de producao.
3. Executar redeploy controlado.
4. Validar health check e fluxo de login/reset.
5. Revogar segredo antigo.

## 6. Evidencias operacionais (3.3)

Registrar periodicamente:
- resultado de `curl -I https://<backend>/health` com headers de seguranca;
- validacao de conexao com Supabase via logs sem queda para conexao insegura;
- validacao de envio Resend sem exposicao de segredo em logs.

## 7. Riscos residuais

- Dependencia de configuracao correta no provedor de hospedagem.
- Necessidade de disciplina operacional para rotacao de segredos.
- Criptografia de coluna para PII ainda nao adotada por padrao.

## 8. Como evitar regressao

- Teste de regressao em auth/reset apos alteracoes de infraestrutura.
- Revisao obrigatoria de variaveis de ambiente antes de deploy.
- Checklist de seguranca aplicado em cada release.
