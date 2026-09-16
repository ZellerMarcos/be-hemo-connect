# Auditoria e Logs

Este documento descreve os controles do requisito 5 para rastreabilidade operacional do Hemo Connect.

## 1. Escopo dos eventos

Os eventos de auditoria sao emitidos pelo backend no logger `app.audit`, em uma linha por evento:

```text
AUDIT | acao=<evento> | status=<sucesso|falha|bloqueado> | ator=<email> | motivo=<codigo>
```

O campo `ator` identifica a conta pelo e-mail quando ele esta disponivel. O campo `motivo` usa codigos operacionais, sem registrar credenciais ou valores temporarios.

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

A aplicacao apenas acrescenta eventos ao fluxo de logs do processo. Ela nao possui endpoint, tela ou rotina para editar ou apagar registros de auditoria.

Em producao, os logs devem ser coletados pelo provedor de hospedagem (Render) e encaminhados para uma plataforma de observabilidade que ofereca controle de acesso, retencao definida e trilha de alteracoes. A configuracao operacional minima e:

1. restringir acesso de leitura e administracao dos logs a pessoas autorizadas;
2. definir retencao conforme politica interna e obrigacoes legais aplicaveis;
3. exportar ou arquivar registros antes da expiracao da retencao;
4. investigar alteracoes de configuracao no provedor por sua trilha administrativa.

A aplicacao nao cria tabela de auditoria no banco e nao executa alteracoes de esquema.

## 4. Exemplo de analise

Exemplo anonimizado de linhas coletadas:

```text
AUDIT | acao=login | status=falha | ator=ana@example.com | motivo=credenciais_invalidas
AUDIT | acao=login | status=bloqueado | ator=ana@example.com | motivo=credenciais_invalidas
AUDIT | acao=2fa_validacao | status=sucesso | ator=joao@example.com
```

Uma investigacao pode filtrar `acao=login` e `status=bloqueado` por periodo para identificar contas que atingiram o limite de tentativas. Em seguida, correlaciona-se o `ator` com os eventos `2fa_validacao` e `logout` da mesma conta. O resultado deve ser tratado como dado operacional sensivel e acessado somente por equipe autorizada.

## 5. Evidencias

- `tests/test_auth.py` valida emissao de eventos de login e 2FA.
- Os testes tambem confirmam que senha e codigo nao aparecem na captura de logs.
- A revisao de producao deve registrar uma amostra anonimizada dos eventos no provedor de logs e a configuracao de retencao adotada.
