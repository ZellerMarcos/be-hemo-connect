# RELEASE - Requisito 5 (Auditoria e Logs)

## Resumo

Esta entrega adiciona persistencia de eventos estruturados de auditoria aos fluxos criticos de autenticacao. A tabela e as triggers devem ser aplicadas manualmente com `sql/create_audit_logs.sql`.

## Itens implementados

### 5.1 Logs de autenticacao registrados
- Login com sucesso, falha de credenciais e bloqueio temporario.
- Encerramento de sessao e sessao invalida ou expirada.
- Solicitacao e resultado de redefinicao de senha.

### 5.2 Logs de falhas e 2FA registrados
- Envio do desafio 2FA com sucesso ou falha.
- Validacao 2FA com sucesso, codigo ausente, invalido ou expirado.
- Eventos de falha com motivo operacional padronizado.

### 5.3 Protecao contra alteracao dos logs
- Eventos persistidos em `audit_logs` e emitidos no logger do processo.
- Hash encadeado com `previous_hash` e `current_hash`.
- Nenhuma rota, tela ou rotina da aplicacao altera ou exclui logs.
- Triggers PostgreSQL bloqueiam `UPDATE` e `DELETE`.

### 5.4 Exemplo de analise de logs apresentado
- `docs/AUDITORIA_E_LOGS.md` inclui formato dos eventos, exemplo anonimizado e procedimento de correlacao para investigacao.

## Formato

```text
AUDIT | acao=<evento> | status=<sucesso|falha|bloqueado> | ator=<email> | motivo=<codigo>
```

Senhas, hashes, codigos 2FA, tokens de reset, URLs de reset e chaves de API nao sao incluidos nos eventos.

## Validacao

- Testes de autenticacao validam os eventos de login e 2FA.
- Testes confirmam que senha e codigo 2FA nao aparecem nos logs capturados.
