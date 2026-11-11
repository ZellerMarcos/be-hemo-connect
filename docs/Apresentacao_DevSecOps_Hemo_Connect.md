# Hemo Connect — DevSecOps Avançado

> Apresentação baseada no *Relatório Técnico DevSecOps Avançado* ([PDF](./Relatorio_DevSecOps_Avancado_Hemo_Connect.pdf)).
> Autores: Marcos Zeller e Willian Donizetti — UMC.

---

## 1. Contexto

- **Backend:** FastAPI, SQLAlchemy, PostgreSQL, Argon2id.
- **Frontend:** React, TypeScript, Vite, npm.
- **Esteira pré-existente (preservada):** testes/build, Semgrep, TruffleHog, Trivy SCA.
- **Novidade:** três jobs independentes **em cada repositório** (backend e frontend):

| Job | Ferramenta | Objetivo |
|-----|-----------|----------|
| DAST | OWASP ZAP 2.17.0 | Testar a aplicação em execução |
| SAST + Privacidade | Bearer 2.1.3 | Segurança de código e dados pessoais (LGPD) |
| Supply chain | Trivy 0.76.1 | Gerar SBOM (CycloneDX 1.7) |

---

## 2. Fluxo da esteira

```
Código versionado
   → Runner Linux (GitHub Actions)
      → Scanners (ZAP / Bearer / Trivy)
         → Relatórios + SBOM
            → Artefatos para download (retenção 14 dias)
               → Checks exigidos na proteção de branch  (⚠ ainda não verificado)
```

**Gatilhos:** PRs para `main`, push em `main` e `workflow_dispatch`.

**Hardening da própria esteira**
- Permissões mínimas (`contents: read`)
- Actions fixadas por commit; imagens por digest; binários/regras por SHA-256
- Timeouts, controle de concorrência e retenção limitada

---

## 3. OWASP ZAP — DAST

**Backend**
- PostgreSQL 16 descartável, *factory* exclusiva de CI (recusa banco remoto, ambiente não-CI e banco já populado).
- Contas sintéticas de doador e administrador; login por senha + 2FA reais.
- E-mails sintéticos em `example.com`; adaptador local não envia nada pela rede.
- 10 leituras autenticadas comprovadas; escopo apenas GET (sem mutações destrutivas).

**Frontend**
- Bundle local, spider + spiderAjax, scan passivo. Não cobre jornadas autenticadas.

**Gate:** bloqueia em *High*, erros/warnings do Automation Framework, falha de execução e relatório ausente/inválido.

**Resultados**
| Alvo | Resultado |
|------|-----------|
| Frontend | 0 High, 2 Medium, 2 Low, 1 Info |
| Backend (doador / admin) | Sem alertas de classe; exit 0 |

⚠ **Degradação observada:** 6% de respostas 5xx e 8% de falhas de rede no perfil doador. Causa identificada para os 500: IDs de hemocentro acima da faixa `INTEGER` do PostgreSQL (`NumericValueOutOfRange`) — problema **pré-existente** de validação de entrada, ainda **não corrigido**.

---

## 4. Bearer — Segurança e Privacidade

- Analisa `app` (backend) e `src` (frontend); falha em severidade **Critical**.
- Pacote de regras oficial fixado por revisão e SHA-256; `no-extract` reduz código nos artefatos.

**Resultados**
- **Backend:** 0 Critical, 4 Medium (`python_lang_exception`, `python_lang_logger`) → exigem triagem de logs/exposição de dados.
- **Frontend:** 2 Critical iniciais (`hardcoded_secret`) eram **falsos positivos** (rotas públicas em `src/routes.ts`). Tratados com exceção pontual por fingerprint, justificada e com reavaliação em 02/12/2026; a regra continua ativa.
- **Gate comprovado:** fixture sintética com “senha” gerou Critical e exit 1.
- **Privacidade:** relatórios gerados; titulares aparecem como `Unknown` → revisão manual necessária. Não é certificação LGPD.

---

## 5. Trivy — SBOM e Supply Chain

| Origem | Componentes |
|--------|-------------|
| Backend (local, Windows/Py 3.12) | 35 |
| Backend (GitHub Actions, Linux) | 34 |
| Frontend (`package-lock.json`, com dev) | 276 |

- Gate valida formato, inventário não vazio, versões e pacotes esperados.
- `requirements.txt` do backend não fixa versões → inventário gerado via `pip freeze` em venv limpa.
- A diferença 35 × 34 é de ambiente/resolução, não inconsistência declarada.
- SBOM **não** certifica ausência de CVEs (Trivy SCA HIGH/CRITICAL segue separado).

---

## 6. Evidências

- Execuções GitHub Actions aprovadas nos dois repositórios (3 jobs verdes cada).
  - Frontend: execução `41639828429` (main, `f9e8da9`)
  - Backend: execução `41640068061` (PR #34, `cd323b0`); artefatos baixados da execução `41641064293` (main, `830734c`)
- SBOMs remotos baixados e validados (SHA-256 confere com o digest do GitHub).
- Gates negativos testados: Bearer Critical sintético; ZAP com alvo indisponível (ZAP exit 2 → gate exit 1).
- Testes: 11 (gates backend), 6 (gates frontend), 74 (regressão), actionlint OK.

---

## 7. Triângulo CIA

- **Confidencialidade:** sessões reais autenticadas e busca por exposição de dados.
- **Integridade:** gates, checksums, versões fixadas, artefatos verificáveis.
- **Disponibilidade:** execução isolada, limites de recursos, registro explícito dos 500 e falhas de rede; sem ataques contra a implantação.

---

## 8. Limitações honestas

- Proteção de branch (checks obrigatórios) **não verificada** — merge bem-sucedido não prova bloqueio.
- Nenhum PR bloqueado por ZAP/Bearer foi demonstrado.
- Bearer usa **Elastic License 2.0** (source-available, não OSI) → alinhar com o docente o requisito “100% open-source”.
- Triagem do DAST pendente (500 por INTEGER, falhas de rede); 4 Medium Bearer e Mediums do ZAP a revisar.
- Inventário LGPD é pontual, não auditoria jurídica.

---

## 9. Próximos passos

1. Alinhar a questão da licença ELv2 com o docente.
2. Corrigir a validação de IDs fora da faixa INTEGER (com teste PostgreSQL) e repetir os scans.
3. Revisar achados Medium e titulares `Unknown`, sem desativar regras para “ficar verde”.
4. Configurar os 3 novos checks como obrigatórios na proteção de `main` e provar o bloqueio com uma falha.
5. Versionar a atualização documental.

---

## Conclusão

A esteira DevSecOps está **implementada e executando** nos dois repositórios, com gates reais e evidências verificáveis. O aceite integral depende de fechar as pendências acima — principalmente a **proteção de branch** e a **triagem da degradação do DAST**.
