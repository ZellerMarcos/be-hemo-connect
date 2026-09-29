# Relatorio Tecnico DevSecOps - Hemo Connect

**Projeto:** Hemo Connect  
**Integrantes:** Marcos Zeller; Willian Donizetti  
**Instituicao:** UMC  
**Ano:** 2026

## 1. Introducao e contextualizacao

O Hemo Connect trata dados pessoais, credenciais derivadas, codigos temporarios
de autenticacao e registros de auditoria. A seguranca da aplicacao depende nao
apenas dos controles implementados no codigo, mas tambem da verificacao continua
das mudancas antes de sua integracao na branch principal.

A esteira DevSecOps adiciona verificacoes automatizadas a cada `push` e `pull
request` direcionado a `main`. Ela nao substitui Argon2id, 2FA, controles de
sessao, LGPD ou auditoria. Ela funciona como uma camada preventiva para detectar
segredos expostos, vulnerabilidades conhecidas em dependencias e padroes
inseguros no codigo Python e TypeScript antes do merge.

## 2. Ferramentas adotadas

### 2.1 TruffleHog - secrets scanning

O TruffleHog analisa o historico Git e os arquivos rastreados para identificar
credenciais verificadas, como chaves de API, tokens e senhas. Um segredo
verificado e bloqueante por natureza: o job termina com codigo diferente de zero
e nao existe configuracao que converta esse resultado em sucesso.

### 2.2 Trivy - software composition analysis

O Trivy analisa os manifests de dependencias Python e npm do monorepo. O job
considera vulnerabilidades de bibliotecas com severidade `HIGH` ou `CRITICAL` e
usa `exit-code: 1`. Vulnerabilidades `LOW` e `MEDIUM` nao bloqueiam a esteira,
mas devem ser acompanhadas conforme o risco do componente.

### 2.3 Semgrep OSS - static application security testing

O Semgrep analisa o codigo-fonte do backend FastAPI e do frontend React usando
os packs comunitarios `p/owasp-top-ten` e `p/cwe-top-25`. Semgrep OSS representa
severidade como `ERROR`, `WARNING` e `INFO`, e nao como `HIGH` ou `CRITICAL`.
Por isso, a politica bloqueante usa `ERROR` com `--error`; `WARNING` e `INFO`
nao interrompem o workflow. Esse comportamento esta documentado para evitar uma
equivalencia de severidade inventada.

## 3. Integracao com os requisitos do Hemo Connect

| Requisito ou controle | Risco | Controle DevSecOps | Ferramenta | Evidencia |
| --- | --- | --- | --- | --- |
| Credenciais e variaveis de ambiente | Exposicao acidental de chaves e senhas no Git | Varredura do historico e arquivos rastreados | TruffleHog | Job `Secrets - TruffleHog` |
| Dependencias FastAPI, SQLAlchemy e npm | CVEs em bibliotecas de terceiros | SCA com bloqueio HIGH/CRITICAL | Trivy | Job `Dependencies - Trivy` |
| APIs FastAPI e SQLAlchemy | Injecao, autenticacao inadequada e padroes inseguros | Regras OWASP e CWE | Semgrep | Job `SAST - Semgrep` |
| Frontend React e TypeScript | XSS e uso inseguro de APIs do navegador | Analise estatica do codigo-fonte | Semgrep | Job `SAST - Semgrep` |
| Hash, 2FA, sessao e reset | Regressao de seguranca em mudancas futuras | Testes do backend em CI | Backend validation | Job `Backend validation` |
| Privacidade, LGPD e auditoria | Exposicao indevida ou regressao de fluxos | Validacao continua e revisao de resultados | Todas | Logs e evidencias do workflow |

Os controles descritos em `SECURITY.md`, `LGPD.md`, `AUDITORIA_E_LOGS.md` e
`CHECKLIST.md` devem ser tratados como controles de aplicacao ou documentacao.
A esteira automatizada complementa esses controles e nao prova, isoladamente,
que todos os requisitos estao implementados.

## 4. Arquitetura da esteira

```text
Developer
   |
Git push / Pull request para main
   |
GitHub Actions - DevSecOps Pipeline
   |
+-------------------------------+
| TruffleHog - Secrets          |
| Trivy - Dependencias / SCA    |
| Semgrep - SAST                |
+-------------------------------+
   |
Validacao backend e frontend
   |
PASS -> Revisao e merge elegiveis
FAIL -> Status check falha; merge bloqueado pelo Ruleset
```

## 5. Evidencias de funcionamento

As evidencias abaixo devem receber capturas reais apos o push do workflow. Nao
foram inseridas imagens ou resultados ficticios neste relatorio.

1. **Workflow no GitHub Actions**: `[INSERIR PRINT REAL DO WORKFLOW AQUI]`
2. **TruffleHog concluido**: `[INSERIR PRINT REAL DO JOB AQUI]`
3. **Trivy concluido**: `[INSERIR PRINT REAL DO JOB AQUI]`
4. **Semgrep concluido**: `[INSERIR PRINT REAL DO JOB AQUI]`
5. **Pipeline geral verde**: `[INSERIR PRINT REAL DO JOB GREEN AQUI]`
6. **Pull request com checks**: `[INSERIR PRINT REAL DO PR AQUI]`
7. **Ruleset/Branch Protection da main**: `[INSERIR PRINT REAL DA CONFIGURACAO AQUI]`

Caso algum alerta seja encontrado, registrar apenas o identificador do alerta,
severidade, componente afetado, impacto, recomendacao e situacao da correcao.
Nunca registrar o valor de uma credencial ou token no relatorio.

## 6. Politica de bloqueio

| Categoria | Politica |
| --- | --- |
| Segredo verificado pelo TruffleHog | Bloqueia sempre. |
| Trivy LOW ou MEDIUM | Nao bloqueia. |
| Trivy HIGH ou CRITICAL | Bloqueia com `exit-code: 1`. |
| Semgrep INFO ou WARNING | Nao bloqueia. |
| Semgrep ERROR | Bloqueia com `--error`. |

O workflow falhar nao bloqueia o merge sozinho. O responsavel pelo repositorio
deve configurar um Ruleset ou Branch Protection em `main`, exigindo os checks
de seguranca e validacao antes do merge.

## 7. Resultados

Na versao inicial deste documento, nao ha resultados de execucao no GitHub
Actions anexados. O resultado final deve ser preenchido somente apos uma
execucao real do workflow, indicando o status de cada job e os achados reais,
caso existam.

## 8. Conclusao

A esteira automatiza a verificacao de segredos, CVEs e padroes de codigo
inseguro, alem de confirmar testes e build existentes. Ela reduz o risco de que
mudancas inseguras avancem para a branch principal, mas nao torna o sistema
automaticamente seguro. A revisao de codigo, a rotacao de segredos, a protecao
de branch e a correcao dos achados continuam necessarias.