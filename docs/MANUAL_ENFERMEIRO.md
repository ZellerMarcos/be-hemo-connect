# Manual do Enfermeiro — Hemo Connect

## Sobre este manual

Este manual orienta o profissional com perfil **ENFERMEIRO** no acompanhamento
e registro da triagem de doadores.

> **Situação do documento:** guia do fluxo previsto na especificação da Visão
> do Enfermeiro. Na versão do backend analisada em 05/10/2026, os módulos de
> triagem, pré-triagem, agendamento e histórico ainda não estão implementados,
> e o frontend não está neste repositório. As instruções dessas etapas devem
> ser validadas na aplicação entregue antes de utilizar este manual em produção.
> Nomes de botões e status abaixo representam a especificação, não telas já
> verificadas.

Este documento explica o uso do sistema. Ele **não substitui protocolos
institucionais, capacitação profissional ou avaliação clínica** e não define
critérios para considerar um doador apto ou inapto.

## 1. Preparação para o acesso

Antes de começar, tenha:

- uma conta pessoal ativa com perfil **ENFERMEIRO**, configurada pelo responsável;
- acesso ao e-mail cadastrado para receber o código de verificação;
- o endereço oficial do Hemo Connect fornecido pela instituição;
- autorização institucional para atender os doadores e consultar seus dados.

Não utilize a conta de outro profissional. Se seu perfil estiver incorreto ou
a área de enfermagem não estiver disponível, solicite orientação ao responsável
pelo sistema; não tente acessar funcionalidades de outro perfil.

## 2. Entrar no sistema

1. Acesse o endereço oficial do Hemo Connect.
2. Informe seu e-mail e sua senha na tela de login.
3. Envie os dados e aguarde a solicitação do segundo fator.
4. Consulte seu e-mail e localize o código de verificação de **seis dígitos**.
5. Digite o código completo, incluindo eventuais zeros no início.
6. Confirme a verificação.
7. No fluxo previsto, você será direcionado à área de enfermagem.

O código vale por **cinco minutos** e só pode ser utilizado uma vez. Um novo
login gera outro código e invalida o anterior. Utilize o código mais recente.
Não compartilhe senha nem código de verificação.

### Dificuldades no login

- **Código não recebido:** verifique a caixa de spam e se está consultando o
  e-mail correto. Se necessário, reinicie o login; persistindo o problema,
  procure o suporte.
- **Código inválido ou expirado:** confira os seis dígitos e faça um novo login
  se o prazo tiver acabado.
- **E-mail ou senha inválidos:** confira os dados antes de repetir a tentativa.
- **Conta bloqueada:** cinco tentativas de senha incorreta em uma janela de
  quinze minutos bloqueiam o login por uma hora. Respeite o período informado.
- **Esqueceu a senha:** utilize a recuperação de senha na tela de acesso, quando
  disponível. O link enviado por e-mail vale por quinze minutos e tem uso único.

## 3. Conhecer a área de enfermagem

A área prevista apresenta a seção **Triagem de Doadores**. Seu fluxo de trabalho
é:

**Consultar a fila → selecionar o doador → conferir os dados → consultar a
pré-triagem e o histórico → iniciar a triagem → registrar a avaliação → escolher
o resultado → finalizar → conferir a confirmação.**

### Indicadores do painel

Quando disponíveis, o painel poderá apresentar:

| Indicador | O que consultar |
| --- | --- |
| Triagens Pendentes | Atendimentos aguardando triagem. |
| Em Atendimento | Triagens em andamento. |
| Triagens Concluídas | Triagens finalizadas conforme a classificação do sistema. |
| Encaminhadas ao Médico | Triagens encaminhadas para avaliação médica. |

Considere os filtros e o período apresentados na tela. Um indicador ausente,
em carregamento ou com erro **não significa que seu valor é zero**.

## 4. Consultar a lista de triagens

1. Abra a lista de triagens na área de enfermagem.
2. Aguarde o carregamento dos registros.
3. Localize o doador que será atendido.
4. Confira o nome, o agendamento e o status antes de abrir o atendimento.
5. Utilize a ação de visualização para consultar os detalhes.

A lista poderá exibir nome, CPF mascarado, data e hora do agendamento, tipo
sanguíneo e status, conforme os dados disponíveis e necessários ao atendimento.

Se a tela oferecer busca, filtros ou paginação:

- pesquise por nome ou CPF, conforme o formato solicitado;
- selecione o status ou período desejado;
- confira se há outras páginas;
- limpe os filtros para voltar à listagem mais ampla.

Se aparecer **“Nenhuma triagem pendente”**, confira os filtros antes de concluir
que não existem doadores aguardando atendimento. Uma mensagem de erro de
carregamento não deve ser interpretada como fila vazia.

## 5. Conferir os dados do doador

Ao abrir os detalhes, confirme que selecionou a pessoa correta, seguindo o
procedimento de identificação da instituição.

A tela poderá apresentar nome, CPF, data de nascimento, telefone, e-mail e tipo
sanguíneo. Consulte somente o necessário ao atendimento.

Se houver divergência ou informação indispensável ausente, solicite orientação
ao responsável. Não preencha dados por suposição nem altere o cadastro de outra
pessoa fora das permissões e do fluxo autorizado.

## 6. Consultar a pré-triagem

Quando disponível, abra a seção **Pré-triagem** e leia todas as respostas
registradas pelo doador, inclusive detalhes complementares e datas.

- As respostas são para **consulta**, não para edição pelo enfermeiro.
- Não interprete resposta ausente como “não”.
- Se identificar divergências, confirme as informações durante o atendimento
  e registre-as no campo de avaliação adequado, quando disponível.
- O questionário não representa aprovação automática para doação. A avaliação
  deve seguir os protocolos da instituição.

Se a pré-triagem estiver indisponível, siga a orientação institucional para
prosseguir; não crie respostas em nome do doador.

## 7. Consultar o histórico

Quando disponível, consulte o histórico de doações e atendimentos. Confira
datas, tipos de registro e resultados apresentados.

O histórico é de **somente leitura** para o enfermeiro, salvo permissão
expressamente existente no sistema. Não altere registros anteriores.

A ausência de registros na tela não comprova que a pessoa nunca doou. Não
confunda indisponibilidade da consulta com inexistência de histórico.

## 8. Iniciar a triagem

1. Confira novamente a identidade do doador e o atendimento selecionado.
2. Verifique se o status permite iniciar a triagem.
3. Selecione **Iniciar Triagem**.
4. Aguarde a confirmação da operação.
5. Confira a mudança para **EM_TRIAGEM**, ou o status equivalente adotado na
   aplicação.
6. Prossiga para o formulário de avaliação.

Não repita o clique enquanto a solicitação estiver em andamento.

Se o sistema informar que outro profissional iniciou o atendimento ou que o
status mudou, atualize a consulta e alinhe a situação com a equipe. Não tente
sobrescrever o atendimento.

## 9. Registrar a avaliação de enfermagem

Preencha somente os campos efetivamente apresentados no formulário.

A especificação cita, como exemplos, observações, pressão arterial, frequência
cardíaca, temperatura e peso. **A existência, obrigatoriedade, unidade e formato
desses campos dependem da implementação e dos protocolos institucionais.**

Durante o preenchimento:

- registre as informações do atendimento correto;
- respeite as unidades e orientações exibidas ao lado dos campos;
- corrija os campos indicados pelas mensagens de validação;
- escreva observações claras, objetivas e pertinentes;
- não invente medidas, respostas, diagnósticos ou justificativas;
- não inclua informações pessoais sem necessidade.

Não presuma que o formulário salva automaticamente. Antes de sair da tela,
confirme se existe uma ação de salvar e se houve confirmação de persistência.
O fluxo especificado prevê a gravação da avaliação na finalização.

## 10. Selecionar o resultado

Escolha o resultado permitido pela aplicação e compatível com a avaliação
realizada, seguindo os protocolos da instituição.

| Resultado previsto | Significado no fluxo do sistema |
| --- | --- |
| **APTO** | Registra o resultado de aptidão da avaliação de enfermagem. Não comprova, por si só, que a doação aconteceu. |
| **INAPTO** | Registra o resultado de inaptidão da avaliação. Informe observação ou justificativa conforme os campos e regras existentes. |
| **ENCAMINHADO_MEDICO** | Encaminha o atendimento para avaliação médica no fluxo disponível. Não representa uma decisão médica. |

Não utilize este manual como critério clínico para escolher o resultado. Não
registre um diagnóstico por suposição nem conclua a avaliação médica em nome
de outro profissional.

### Referência dos status previstos

| Status | Como interpretar |
| --- | --- |
| **AGUARDANDO_TRIAGEM** | Atendimento aguardando início da triagem. |
| **EM_TRIAGEM** | Avaliação de enfermagem em andamento. |
| **APTO** | Resultado de aptidão registrado. |
| **INAPTO** | Resultado de inaptidão registrado. |
| **ENCAMINHADO_MEDICO** | Atendimento encaminhado para avaliação médica. |
| **CONCLUIDO** | Etapa ou atendimento concluído conforme a regra adotada pelo sistema. |

Esses nomes são referências da especificação. A aplicação pode reutilizar
status equivalentes. **APTO** e **CONCLUIDO** não devem ser tratados como
sinônimos sem confirmação do fluxo adotado.

## 11. Finalizar a triagem

Antes de finalizar, revise:

- a identidade do doador;
- os campos obrigatórios e os valores registrados;
- as observações e justificativas pertinentes;
- o resultado selecionado.

Em seguida:

1. Selecione a ação de finalização disponível.
2. Confirme a operação, se a interface solicitar.
3. Aguarde o processamento, sem clicar novamente.
4. Confira a mensagem **“Triagem finalizada com sucesso.”**, ou equivalente.
5. Verifique se o status atualizado corresponde ao resultado escolhido.
6. Retorne à lista e confira a atualização do atendimento.

Não considere a triagem salva apenas porque os dados foram digitados ou porque
o botão foi acionado.

Se houver erro, perda de conexão ou dúvida sobre o resultado da solicitação,
consulte novamente o atendimento antes de reenviar. Se os dados ou o status não
corresponderem ao esperado, procure o suporte. Não presuma que uma triagem
finalizada possa ser reaberta ou editada: isso depende das regras disponíveis.

## 12. Sessão, saída e privacidade

O backend atual utiliza um limite de **45 minutos sem atividade válida**. Ao
receber uma mensagem de sessão expirada, faça login novamente e confira o estado
do atendimento antes de continuar. Não presuma que dados ainda não confirmados
tenham sido salvos.

Ao terminar o trabalho, use a ação de sair disponível na aplicação. Não trate
o fechamento da aba como substituto do logout.

Para proteger os dados:

- utilize apenas o endereço oficial, com HTTPS no ambiente de produção;
- não compartilhe sua conta, senha ou código de verificação;
- bloqueie a estação ao se afastar;
- não fotografe, copie ou encaminhe dados de doadores para canais não autorizados;
- consulte somente dados necessários ao atendimento;
- não inclua informações clínicas completas em chamados de suporte;
- não tente contornar bloqueios de acesso ou permissões.

## 13. Resolver problemas durante o atendimento

| Situação | Orientação |
| --- | --- |
| Painel ou lista em carregamento | Aguarde antes de repetir ações. |
| Erro ao carregar dados | Tente novamente pela ação disponível; persistindo o erro, acione o suporte. |
| Doador não encontrado | Confira busca, filtros, período e paginação; depois confirme com a equipe responsável. |
| Acesso negado | Confira a conta utilizada e solicite verificação das permissões. |
| Triagem já em atendimento | Atualize a consulta e alinhe com o profissional responsável. |
| Formulário com erro de validação | Corrija os campos indicados conforme as orientações da tela. |
| Falha ou dúvida na finalização | Consulte o registro para verificar se a operação foi concluída antes de reenviar. |
| Sessão expirada | Faça novo login e confira o estado do atendimento. |

No chamado de suporte, informe a ação tentada, o horário aproximado e a mensagem
apresentada. Use somente os identificadores necessários pelo canal autorizado.
Nunca envie senha, código 2FA ou link de recuperação de senha.

## 14. Checklist rápido do atendimento

- [ ] Entrei com minha própria conta e perfil de enfermeiro.
- [ ] Selecionei e identifiquei corretamente o doador.
- [ ] Consultei a pré-triagem e o histórico, quando disponíveis.
- [ ] Confirmei o início da triagem.
- [ ] Registrei a avaliação nos campos disponíveis.
- [ ] Escolhi o resultado conforme o protocolo institucional.
- [ ] Revisei os dados antes de finalizar.
- [ ] Recebi confirmação e conferi o status atualizado.
- [ ] Ao encerrar o uso, saí da aplicação.

## 15. Validação antes da distribuição

O responsável pela entrega deve validar este manual com as telas reais,
confirmando:

- acesso exclusivo e autorizado à área de enfermagem;
- nomes de menus, botões, status e mensagens;
- disponibilidade de indicadores, filtros, pré-triagem e histórico;
- campos, unidades, obrigatoriedade e comportamento de salvamento;
- regras de início, finalização e encaminhamento médico;
- funcionamento da expiração de sessão e do logout;
- canal oficial de suporte.

Enquanto essas verificações não forem concluídas, este documento permanece
como **guia do fluxo previsto**, não como comprovação de funcionalidades entregues.
