# Plano de execucao - DevSecOps avancado open-source

Data: 02/11/2026.

## 1. Objetivo e escopo

Implementar DAST com OWASP ZAP, analise estatica de seguranca/privacidade
com Bearer CLI e geracao de SBOM com Trivy no GitHub Actions. Produzir
relatorio tecnico PDF com evidencias reais de execucao e download.

Este documento e somente o plano solicitado. Nao implementa workflows,
executa scanners, altera regras do GitHub ou produz evidencias de aprovacao.

Escopo proposto: os dois repositorios, com tres jobs novos em cada um:

- Backend: `ZellerMarcos/be-hemo-connect`, FastAPI/Python/PostgreSQL.
- Frontend: `ZellerMarcos/fe-hemo-connect`, React/TypeScript/Vite/npm.

Preservar os workflows existentes de testes, lint/build, Semgrep,
TruffleHog e Trivy SCA. Acrescentar um workflow avancado em cada
repositorio, evitando executar novamente a mesma verificacao SCA sem motivo.
O relatorio consolidado apresentara as duas execucoes, distinguindo a
cobertura de API da cobertura da interface web.

## 2. Criterios de avaliacao e aceite

| Criterio da imagem | Peso | Entrega planejada | Evidencia de aceite |
| --- | --- | --- | --- |
| Configuracao do pipeline | 35% | YAML valido, aplicacao iniciada e jobs ZAP, Bearer e Trivy SBOM automatizados. | Execucao real dos tres jobs verdes em cada repositorio; URL, commit e data identificados. |
| Geracao de artefato e bloqueio | 25% | Gate de falha correto, `sbom.json` valido e upload para Actions. | Teste positivo/negativo dos gates; artefato listado, baixado e conferido. |
| Qualidade do relatorio | 40% | PDF com clareza tecnica, ferramentas, requisitos, justificativas e prints. | PDF legivel, fontes referenciadas, resultados reais e limitacoes explicitadas. |

Requisitos minimos:

1. ZAP e Bearer bloqueiam o check quando o limiar definido e atingido.
2. Falha de scanner, startup, relatorio ausente ou SBOM vazio nunca produz
   resultado verde.
3. SBOM usa CycloneDX JSON, com nome de arquivo exato `sbom.json`.
4. Relatorios e SBOM ficam disponiveis para download; upload nao mascara falhas.
5. Os tres checks avancados sao obrigatorios para merge na branch protegida,
   conforme disponibilidade de rulesets/branch protection do plano GitHub.
6. Se houver deploy automatizado, ele depende do sucesso desses checks.
   Sem deploy automatizado, o gate impede merge; nao se afirma que o build
   local foi impedido ou que uma implantacao manual ficou impossivel.

## 3. Arquitetura gratuita e open-source

```text
Push / Pull Request / workflow_dispatch
                  |
        Workflow avancado de cada repositorio
                  |
     +------------+------------+
     |            |            |
 ZAP DAST    Bearer CLI    Trivy SBOM
     |            |            |
 App local    Codigo       Dependencias
 descartavel  versionado   resolvidas
     |            |            |
 Relatorios   Relatorio    sbom.json
     +------------+------------+
                  |
       Upload de artefatos + checks
                  |
     Merge/deploy condicionado ao sucesso
```

- Usar runners Linux padrao do GitHub, ferramentas gratuitas e artefatos
  do Actions; nao exigir Bearer Pro, ZAP comercial, API keys de scanners
  ou servicos externos pagos.
- GitHub Actions e a plataforma de orquestracao, nao um produto integralmente
  open-source. ZAP e Trivy sao open-source; Bearer 2.1.3 e seu pacote de
  regras usam Elastic License 2.0 (source-available, nao aprovada pela OSI).
  Manter Bearer conforme enunciado, mas alinhar essa incompatibilidade com
  o requisito literal "100% open-source" antes do aceite. Verificacao local:
  https://github.com/Bearer/bearer/blob/v2.1.3/LICENSE.txt.
- Runners padrao sao gratuitos para repositorios publicos. Se privados,
  verificar franquia de minutos/armazenamento e impedir gasto excedente;
  nao prometer uso ilimitado gratuito. Nao tornar codigo privado publico
  apenas para obter gratuidade.
- Fixar Actions por SHA e imagens/binarios por versao e digest/checksum
  verificados. Escolher versoes disponiveis na implementacao, sem depender
  de tags `latest` ou copiar versoes antigas sem validacao.
- Usar `permissions: contents: read`, timeouts, cancelamento de execucoes
  superadas e retencao inicial de artefatos de 14 dias.
- Nao usar `pull_request_target` para executar codigo de PR nem runners
  persistentes que tenham acesso a producao.

## 4. Execucao tecnica por job

### 4.1 ZAP - DAST

**Backend: alvo principal de testes ativos.**

1. Iniciar PostgreSQL descartavel no job, com credenciais sinteticas e
   schema criado a partir dos modelos somente no ambiente de CI.
2. Criar bootstrap exclusivo de testes, reutilizando helpers existentes
   quando adequados. Nao depender das migrations operacionais ausentes
   nem concluir que esse bootstrap valida o deploy/migrations de producao.
3. Inicializar a API com banco do job e adaptador de e-mail local controlado.
   Nunca enviar mensagens pelo Brevo real nem carregar segredos de producao.
4. Nao usar apenas `APP_ENV=test` e `/health`: a configuracao atual usa
   SQLite em memoria e o health nao prova que o schema e as rotas funcionam.
   Validar conexao, schema, `/openapi.json` e uma jornada funcional antes do scan.
5. Criar dados sinteticos e autenticar pelos fluxos reais de senha + 2FA.
   Capturar o codigo apenas no adaptador de e-mail do ambiente de teste.
   Nao criar endpoint publico de bypass nem desabilitar autenticacao,
   autorizacao, rate limiting ou controles da aplicacao para obter verde.
6. Configurar contexto ZAP restrito ao host/porta local do job. Importar
   OpenAPI, fornecer IDs/corpos sinteticos validos e executar scan ativo
   das rotas autorizadas, incluindo chamadas autenticadas.
7. Usar sessoes de contas de teste diferentes quando necessario para
   separar autossservico e administracao. Nao aplicar token global a
   destinos externos; mascarar tokens e evitar gravar sessoes em artefatos.
8. Executar no Automation Framework: importacao OpenAPI, requisicoes de
   preparacao, active scan, espera de passive scan, report e exitStatus.
   Verificar a configuracao exata na versao fixada antes de publicar o YAML.
9. Gerar JSON e HTML; comprovar rotas efetivamente visitadas. Scan de
   `/health` ou apenas respostas 401/429 nao e cobertura funcional suficiente.
10. Ajustar o ritmo do scan aos limites reais; renovar sessoes/desafios
    por fluxo legitimo quando necessario. Registrar bloqueios por 429
    como limite de cobertura, sem desligar os controles.

**Frontend: DAST da interface servida no runner.**

1. Executar `npm ci`, build com `VITE_API_URL` de teste e servir o bundle
   apenas localmente, sem chamar a API implantada.
2. Executar ZAP baseline/passive scan com descoberta compativel com SPA,
   incluindo spider de navegador quando suportado pela imagem escolhida.
3. Verificar que paginas/assets foram visitados, nao apenas o HTML inicial.
4. Registrar que este job cobre interface, headers e recursos entregues.
   Jornadas autenticadas de ponta a ponta ficam no ambiente API+cliente
   de homologacao; nao declarar que o scan estatico do bundle as exercitou.
5. Se for necessario cobrir a SPA autenticada no CI, estender esse job
   para subir backend descartavel de commit fixado e registrar a dupla
   de commits, sem usar a API de producao.

**Bloqueio ZAP:**

- ZAP usa Informational, Low, Medium e High; nao possui nivel Critical.
  Mapear a exigencia de falha critica para High, seu maior nivel.
- Usar `exitStatus` do Automation Framework com `errorLevel: High`,
  `errorExitValue: 1` e `okExitValue: 0`.
- Medium/Low permanecem no relatorio como achados a tratar. Warnings de
  operacao do scanner nao podem ser confundidos com achados Low/Medium:
  devem ser triados antes de permitir sucesso.
- Se o frontend usar o script baseline em vez do Automation Framework,
  tratar explicitamente seus codigos 0/1/2/3 e aplicar um gate sobre o
  JSON completo para risco High; codigo 3 sempre falha. Nao usar `|| true`.
- Validar que o relatorio existe, e parseavel e contem evidencia de scan;
  nenhum scanner interrompido ou alvo indisponivel passa pelo gate.
- Excecoes somente por regra/instancia justificada, com dono e prazo;
  nao ignorar todas as regras ou remover alertas High para fabricar verde.

### 4.2 Bearer CLI - Seguranca e privacidade no codigo

1. Escanear `app` no backend e `src` no frontend usando a CLI gratuita,
   com a ressalva de licenciamento ELv2 documentada acima.
2. Excluir apenas dependencias, caches, bundles gerados e resultados de
   scanners; nao excluir modulos de autenticacao, logs ou privacidade.
3. Gerar relatorio JSON e resumo legivel no job, com regras, severidade
   e localizacao dos achados.
4. Configurar gate equivalente a
   `--fail-on-severity critical --exit-code 1`; manter High/Medium/Low
   visiveis no relatorio. Confirmar essas opcoes na versao fixada e nao
   presumir que a Action exponha todos os argumentos da CLI.
5. Executar scan e manter o codigo de saida, publicar relatorio mesmo
   em falha e depois preservar o resultado do gate.
6. Revisar achados de logs, trafego, armazenamento, CPF/e-mail, dados de
   saude e segredos, com evidencias sanitizadas e sem dados reais.
7. Confirmar cobertura real da linguagem/framework. A documentacao cita
   Python/Django e JavaScript/TypeScript/React; nao garante analise completa
   de FastAPI/SQLAlchemy. A CLI gratuita nao oferece toda a analise
   cross-file da edicao Pro. Documentar lacunas sem trocar para servico pago.

Bearer e uma ferramenta estatica com regras de seguranca e dados
sensíveis; nao substitui inventario LGPD, base legal, consentimentos,
retencao, direitos do titular nem avaliacao juridica.

### 4.3 Trivy - SBOM e cadeia de suprimentos

1. Frontend: usar `package-lock.json` versionado e validado por `npm ci`,
   incluindo dependencias diretas/transitivas e declarando o escopo de dev.
2. Backend: as dependencias atuais nao tem versoes. Preparar ambiente
   virtual limpo exclusivamente com dependencias da aplicacao, resolver
   versoes e gerar manifest `requirements.txt` temporario via `pip freeze`
   em diretorio de inventario. Instalar scanners fora desse ambiente.
3. Gerar o SBOM desse manifest resolvido, nao somente do arquivo original
   sem versoes. O Trivy nao resolve transitivas de um requirements comum
   e por padrao identifica versoes exatas com `==`.
4. Registrar que o SBOM backend retrata a resolucao daquela execucao.
   Como melhoria diretamente relacionada, avaliar versionar um lock
   gerado por ferramenta de pacote e consumi-lo no CI, preservando os
   runtimes existentes; nao mudar de gerenciador sem necessidade.
5. Executar comando equivalente a
   `trivy fs --format cyclonedx --output sbom.json <diretorio-alvo>`,
   adaptado aos caminhos de cada runner.
6. Validar JSON e estrutura CycloneDX; exigir componentes nao vazios,
   nomes e versoes e conferir pacotes representativos, como FastAPI/
   SQLAlchemy no backend e React/Vite no frontend. Definir a lista de
   componentes esperados antes da verificacao.
7. Nao produzir SBOM filtrado somente por HIGH/CRITICAL. Inventario
   completo e diferente de relatorio de vulnerabilidades.
8. Preservar o SCA existente que bloqueia HIGH/CRITICAL. Se analisar
   o SBOM com `trivy sbom`, registrar isso como etapa distinta da geracao.
9. Publicar artefatos separados `sbom-backend` e `sbom-frontend`, cada
   um contendo o arquivo exato `sbom.json` e metadados de commit/versao.
10. Usar upload com erro para arquivo ausente; testar download e conteudo
    descompactado. Artefato publicado vazio ou so com logs nao atende.

## 5. Auditoria LGPD e conexao com os requisitos do projeto

| Requisitos originais | Contribuicao da atividade | Limite que deve constar no relatorio |
| --- | --- | --- |
| 1.5-1.11, 2.1-2.7 | DAST exercita rotas de autenticacao/recuperacao e comportamento de erros; Bearer procura padroes inseguros. | Scanner nao substitui testes de titularidade, uso unico, concorrencia e revogacao existentes. |
| 3.1-3.8 | ZAP identifica problemas observaveis de comunicacao/headers; Bearer examina usos de criptografia/trafego. | HTTP local de CI nao prova HTTPS, TLS do banco, chaves ou repouso em producao. |
| 4.1-4.3 | Bearer auxilia na identificacao de tratamento e exposicao; revisao manual completa inventario/finalidade/minimizacao. | Zero achados nao prova ausencia de dados pessoais ou conformidade LGPD. |
| 4.4-4.11 | Revisao manual compara consentimento, revogacao, exportacao/exclusao e efeitos reais nos fluxos. | Exige evidencias funcionais e politica; nao e resolvido apenas adicionando Bearer. |
| 5.1-5.4 | Analise de logs e erros e complementar aos controles de auditoria. | Nao comprova append-only, integridade concorrente ou retencao operacional. |
| 6.2, 6.6-6.12 | Arquitetura da esteira, SBOM, ameacas, testes, resultados, justificativas e referencias no PDF. | SBOM e inventario de componentes, nao prova ausencia de CVEs nem de adulteracao. |

Incluir inventario resumido de CPF, e-mail, COREN, dados de saude,
consentimentos, logs e exportacoes efetivamente presentes, indicando
entrada, finalidade, armazenamento, destinatario e retencao conhecida.
Marcar pendente o que nao tiver evidencia; dados de saude merecem
classificacao propria. Nao anexar dados pessoais reais ao relatorio.

Relacionar as frentes CIA: ZAP/Bearer contribuem para confidencialidade e
integridade; SBOM/SCA para integridade da cadeia e riscos de disponibilidade.
Nao reclassificar como concluidas as pendencias operacionais P0/P1/P2
da [release anterior](releases/RELEASE_AVALIACAO_VIA_IA_TRIADE_CIA.md).

## 6. Sequencia de execucao

Prazos relativos: D1 e o primeiro dia de execucao apos aprovacao deste plano.
Nao reutilizar as datas vencidas da atividade CIA anterior.

| Etapa | Janela proposta | Responsavel sugerido | Dependencias | Entrega/aceite |
| --- | --- | --- | --- | --- |
| A0 - Baseline e contratos | D1, inicio | Lider tecnico + QA | Nenhuma | Commits, visibilidade/cotas, versoes, thresholds, escopo e nomes de checks definidos. |
| A1 - Ambiente DAST isolado | D1-D2 | Backend + QA | A0 | Banco/schema/dados sinteticos, e-mail local e API funcional sem acesso a producao. |
| A2 - Bearer e revisao de privacidade | D1-D3 | Backend/frontend + privacidade | A0 | Scans dos dois repositorios, triagem e gate Critical comprovado. |
| A3 - SBOM e artefatos | D1-D3 | DevSecOps | A0 | Dependencias resolvidas, dois SBOMs validos e upload/download testados. |
| A4 - ZAP e cobertura | D2-D4 | DevSecOps + QA | A1; A0 para frontend | API ativa e interface escaneadas, reports e gate High comprovados. |
| A5 - Integracao e bloqueio no GitHub | D4 | Lider tecnico + mantenedor GitHub | A2-A4 | Tres checks por repositorio, testes de falha e sucesso e protecao de merge configurada. |
| A6 - Evidencias e relatorio PDF | D5 | Equipe academica + QA | A5 | Prints reais, SBOM baixado, PDF final revisado contra a rubrica. |

Janela inicial: cinco dias uteis com frentes paralelas; estimativa de
8-13 dias-pessoa. Reestimar apos A0/A1. Correcoes de vulnerabilidades reais
e acessos administrativos indisponiveis podem ampliar o prazo; nao
garantir jobs verdes antes de triagem e correcao.

## 7. Validacao obrigatoria

1. Validar YAML/workflows com ferramenta apropriada, como actionlint,
   e os planos de ZAP com a imagem fixada.
2. Reexecutar testes backend e lint/build frontend somente nas superficies
   alteradas; ampliar para suites integradas apos wiring final.
3. Testar gates com relatorios sinteticos isolados: ZAP High retorna 1,
   Bearer Critical retorna 1 e relatorio abaixo do limiar passa.
   Nunca adicionar vulnerabilidade a codigo de producao para esse teste.
4. Testar caminho real de scanner, nao apenas o parser: entradas
   sinteticas de teste ou alvos oficiais descartaveis/autorizados quando
   necessarios, mantidos fora do escopo normal de scan da aplicacao.
5. Testar alvo desligado, falha de ferramenta, timeout, relatorio ausente/
   invalido e SBOM sem componentes: todos devem falhar.
6. Verificar upload em falha usando `if: always()` quando adequado,
   sem `continue-on-error` global nem supressao do exit code.
7. Conferir scan sem segredos e sem trafego para API/banco/e-mail reais.
   Restringir escopo de destino, redirects e egress do ambiente DAST.
8. Executar em PR de teste sem segredos, verificar check vermelho e
   impedimento de merge pela regra do GitHub; depois executar codigo
   corrigido e obter os tres jobs verdes.
9. Baixar ambos os artefatos, validar `sbom.json` e registrar correspondencia
   de commit entre codigo, resultados e prints.
10. Confirmar que o scan nao ficou verde por falta de regras, cobertura
    vazia, respostas apenas 401/429 ou bypass criado para o CI.

## 8. Relatorio tecnico PDF

Produzir fonte editavel no backend, arquivo PDF final e pasta de evidencias
sanitizadas. Nomes propostos: `RELATORIO_DEVSECOPS_AVANCADO.md`,
`Relatorio_DevSecOps_Avancado_Hemo_Connect.pdf` e
`evidencias/devsecops-avancado`, dentro de `docs`.

Estrutura obrigatoria e complementos:

1. Capa: projeto, integrantes, instituicao, data e commits avaliados.
2. Introducao a arquitetura: stack, fronteiras, jobs, gratuidade e isolamento.
3. Descritivo das ferramentas: ZAP DAST, Bearer estatico/privacidade,
   Trivy CycloneDX/SBOM; versoes, opcoes, cobertura e limitacoes.
4. Integracao com requisitos: matriz da secao 5 e conexao CIA/LGPD.
5. Politica de bloqueio: Critical Bearer, High ZAP, falhas operacionais,
   regras de merge/deploy e gestao de excecoes.
6. Resultados: achados reais, triagem/correcoes, contagens e riscos residuais.
7. Evidencias obrigatorias:
   - Print de Actions com os tres jobs verdes por repositorio.
   - Print do artefato SBOM disponivel para download.
   - Conteudo validado do `sbom.json`, identificando componentes e formato.
   - URL de run, commit, data e legenda em cada evidencia.
8. Evidencia opcional de PR bloqueado por falha real. Distinguir teste
   sintetico de vulnerabilidade real; nao rotular simulacao como incidente.
9. Conclusao com alcance e pendencias; nenhum claim de certificacao LGPD.
10. Referencias oficiais normalizadas e data de consulta.

Capturar prints somente apos execucoes reais. Nao montar imagens de jobs
verdes, reutilizar prints de outra revisao ou apresentar artefato nao baixado
como validado. Revisar PDF renderizado quanto a legibilidade, cortes,
links, legendas e ausencia de dados reais/credenciais.

## 9. Definicao de pronto

- Workflows e configuracoes persistidos nos dois repositorios.
- ZAP, Bearer e SBOM executados, com gates positivos/negativos comprovados.
- Achados bloqueadores corrigidos ou excecoes especificas formalmente
  justificadas; resultado verde nunca obtido por ocultacao.
- Checks de merge obrigatorios comprovados, quando suportados; eventual
  limitacao do plano GitHub documentada como impedimento, nao como sucesso.
- SBOMs completos para o escopo declarado e downloads conferidos.
- Prints e PDF vinculados aos commits/runs reais e revisados pela rubrica.
- Ambiente temporario encerrado e arquivos de credenciais de teste removidos.

## 10. Referencias tecnicas verificadas

Consulta em 02/11/2026; confirmar compatibilidade com as versoes selecionadas.

- [ZAP API scan: OpenAPI, scan ativo e exit codes](https://www.zaproxy.org/docs/docker/api-scan/).
- [ZAP Baseline: descoberta e scan passivo](https://www.zaproxy.org/docs/docker/baseline-scan/).
- [ZAP Automation Framework: exitStatus](https://www.zaproxy.org/docs/desktop/addons/automation-framework/job-exitstatus/).
- [Bearer CLI: comandos e politica de falha](https://docs.bearer.com/reference/commands/).
- [Bearer: linguagens/frameworks e limites das edicoes](https://docs.bearer.com/reference/supported-languages/).
- [Bearer: integracao GitHub Actions](https://docs.bearer.com/guides/github-action/).
- [Trivy: filesystem e geracao de SBOM](https://trivy.dev/docs/latest/target/filesystem/).
- [Trivy: dependencias Python e transitivas](https://trivy.dev/docs/latest/coverage/language/python/).
- [GitHub Actions: gratuidade e limites de uso](https://docs.github.com/en/actions/concepts/billing-and-usage).
