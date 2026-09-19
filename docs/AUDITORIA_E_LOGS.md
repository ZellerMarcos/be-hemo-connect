# Auditoria e Logs

Este documento descreve os controles do requisito 5 para rastreabilidade operacional do Hemo Connect.

## 1. Escopo dos eventos

Os eventos de auditoria sao persistidos pelo backend na tabela `audit_logs` e tambem emitidos no logger `app.audit` para observabilidade. Cada registro possui hash SHA-256 encadeado ao evento anterior:

```text
AUDIT | acao=<evento> | status=<sucesso|falha|bloqueado> | ator=<email> | motivo=<codigo>
```

O campo `ator` identifica a conta pelo e-mail quando ele esta disponivel. O campo `motivo` usa codigos operacionais, sem registrar credenciais ou valores temporarios. A migration manual esta em `sql/create_audit_logs.sql`.

| Evento | Quando e registrado |
|---|---|
| `login` | Credenciais validas, credenciais invalidas ou conta bloqueada |
| `2fa_envio` | Emissao e entrega do desafio de segundo fator |
| `2fa_validacao` | Confirmacao, ausencia, expiracao ou falha do codigo 2FA |
| `sessao` | Sessao invalida ou expirada por inatividade |
| `logout` | Encerramento explicito da sessao |
| `reset_senha_solicitacao` | Solicitacao valida ou usuario indisponivel |
| `reset_senha` | Redefinicao concluida ou rejeitada |

## 2. Protecao de dados nos logs

O helper `app.security.audit.registrar_evento` aceita somente campos controlados pela aplicacao. Os fluxos nao registram:

- senhas em texto puro ou hashes de senha;
- codigos 2FA;
- tokens ou URLs de redefinicao;
- chaves de API e demais segredos de ambiente.

Os testes de regressao verificam explicitamente que senha e codigo 2FA nao sao emitidos.

## 3. Integridade e retencao

A aplicacao apenas acrescenta eventos ao banco. A tabela deve ser criada com as triggers do SQL manual, que bloqueiam `UPDATE` e `DELETE`. O campo `previous_hash` referencia o hash anterior e `current_hash` permite verificar adulteracao.

Em producao, os logs devem ser coletados pelo provedor de hospedagem (Render) e encaminhados para uma plataforma de observabilidade que ofereca controle de acesso, retencao definida e trilha de alteracoes. A configuracao operacional minima e:

1. restringir acesso de leitura e administracao dos logs a pessoas autorizadas;
2. definir retencao conforme politica interna e obrigacoes legais aplicaveis;
3. exportar ou arquivar registros antes da expiracao da retencao;
4. investigar alteracoes de configuracao no provedor por sua trilha administrativa.

O backend nao executa alteracoes de esquema automaticamente. O operador deve executar manualmente `sql/create_audit_logs.sql` no PostgreSQL/Supabase antes do deploy.

## 4. Exemplo de analise

Exemplo anonimizado de linhas coletadas:

```text
AUDIT | acao=login | status=falha | ator=ana@example.com | motivo=credenciais_invalidas
AUDIT | acao=login | status=bloqueado | ator=ana@example.com | motivo=credenciais_invalidas
AUDIT | acao=2fa_validacao | status=sucesso | ator=joao@example.com
```

Uma investigacao pode filtrar `acao=login` e `status=bloqueado` por periodo para identificar contas que atingiram o limite de tentativas. Em seguida, correlaciona-se o `ator` com os eventos `2fa_validacao` e `logout` da mesma conta. O resultado deve ser tratado como dado operacional sensivel e acessado somente por equipe autorizada.

## 5. Evidencias

- `tests/test_auth.py` valida que eventos de login, 2FA e sessao sao persistidos em `audit_logs`.
- O mesmo teste verifica o encadeamento de `previous_hash` e `current_hash`.
- Os testes tambem confirmam que senha e codigo nao aparecem na captura de logs.
- A revisao de producao deve registrar uma amostra anonimizada dos eventos no provedor de logs e a configuracao de retencao adotada.
