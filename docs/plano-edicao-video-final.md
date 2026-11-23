# Plano de edição da nova apresentação em vídeo

## Objetivo

Este documento transforma a gravação atual em uma versão final entre **8 e 9
minutos**, coerente com a implementação do protótipo, os requisitos acadêmicos
e os limites técnicos já validados. A meta de 9 minutos é preferencial; se o
prazo apertar, a versão mínima de 7 minutos preserva todos os pontos críticos.

Arquivo de origem analisado:
`data/video/FIAP-TC-FASE-4-video.mp4`.

Princípio central: mostrar **funcionamento de software para revisão humana**,
sem apresentar heurísticas ou testes sintéticos como diagnóstico, detecção
clínica validada ou comunicação efetiva com uma equipe médica.

## Plano de execução com prazo em 23/11/2026

Prazo final: **23/11/2026 às 23:59**.  
Restrição: trabalho presencial das **08:30 às 18:00**.

### Decisão recomendada

Não tentar produzir uma gravação inteiramente nova. Entregar uma versão
**mínima viável e coerente** entre **8 e 9 minutos**, aproveitando as melhores
capturas existentes e gravando apenas o conteúdo que ficou desatualizado ou
criticamente ausente.

Prioridade absoluta:

1. corrigir a abertura e os limites;
2. manter fisioterapia, voz e leito/fusão;
3. acrescentar evolução sintética e FHIR/webhook em um bloco curto;
4. encerrar com testes e limitações;
5. renderizar e validar antes de 22:00.

### Plano de tempo realista

| Quando | Trabalho | Resultado esperado |
|---|---|---|
| 22/11, 21:20–21:40 | Preparar arquivos, abrir o roteiro e limpar a biblioteca demonstrativa | Ambiente pronto sem decisões durante a gravação |
| 22/11, 21:40–22:35 | Regravar fisioterapia, voz e evolução/FHIR em clipes separados | Quatro clipes curtos já atualizados |
| 22/11, 22:35–23:00 | Gravar narrativas e encerramento da abertura, limites e resultados | Locuções completas |
| 22/11, 23:00–23:15 | Fazer backup dos arquivos e confirmar que todos os clipes abrem | Risco de gravação perdido reduzido |
| 23/11, 08:30–18:00 | Trabalho; não planejar edição nesse período | Nenhuma dependência durante o expediente |
| 23/11, 18:15–19:15 | Montar a ordem final com cortes do vídeo original e clipes novos | Linha do tempo completa de 8–9 minutos |
| 23/11, 19:15–20:00 | Inserir títulos, avisos e cortes | Versão visual pronta |
| 23/11, 20:00–20:20 | Ajustar áudio e mixar | Voz inteligível e sem picos |
| 23/11, 20:20–20:50 | Assistir uma vez do início ao fim e anotar erros | Lista curta de correções |
| 23/11, 20:50–21:30 | Corrigir somente erros críticos e exportar | MP4 final |
| 23/11, 21:30–22:00 | Reabrir o MP4 final e revisar por amostragem em três pontos | Arquivo validado |
| 23/11, 22:00–22:30 | Upload e verificação da reprodução | Link funcional |
| 23/11, 22:30–23:30 | Margem para lentidão de upload ou reexportação | Reserva de segurança |
| 23/11, 23:30–23:55 | Atualizar material/documentação com o link final | Entrega pronta |

### Versão mínima viável

Se faltar tempo, use a seguinte montagem sem buscar novas melhorias:

| Bloco | Tempo | Fonte |
|---|---:|---|
| Abertura e limites | 30 s | Nova narração e capa |
| Fluxo/arquitetura | 35 s | Reuso do vídeo atual |
| Fisioterapia | 75 s | Nova gravação ou reuso melhor |
| Voz | 65 s | Nova gravação curta |
| Leito/fusão/histórico | 105 s | Reuso do vídeo atual |
| Evolução/FHIR | 60 s | Nova gravação curta |
| Testes e limitações | 35 s | Novo slide |
| Encerramento | 15 s | Nova narração |
| **Total** | **7 min** | Em torno de 7 minutos; pode chegar a 8–9 com respiração |

### O que não pode ser cortado

- aviso de protótipo acadêmico;
- distinção entre comparação acústica e detecção clínica;
- evento de fisioterapia com relatório;
- incidente imagem–fala e correlação temporal;
- dados/FHIR sintéticos;
- limitação “Aceito pelo destino”;
- contagens finais dos testes;
- limites clínicos e institucionais;
- encerramento acadêmico.

### O que cortar primeiro se a edição atrasar

1. upload de arquivos;
2. toda espera por processamento;
3. terminal e explorador;
4. importação manual CSV/JSON;
5. roteiro longo de arquitetura;
6. repetição de alertas individuais;
7. animações, música e títulos elaborados;
8. regravação perfeita da fala; preserve uma locução clara mesmo com pequena
   diferença de tom.

### Critério de encerramento

Às **21:30**, pare de melhorar o conteúdo e exporte. Depois dessa hora,
somente corrija:

- arquivo sem áudio;
- corte que deixa uma frase incompleta;
- informação tecnicamente incorreta;
- tela ilegível por mais de três segundos;
- segredo, identificador real ou dado pessoal visível;
- vídeo que não reproduz ou formato incompatível.

Não refaça gravações por razões estéticas depois das 21:30.

## Estrutura recomendada

| Cena | Duração-alvo | Origem | Ação |
|---|---:|---|---|
| 1. Abertura e posicionamento | 30 s | Nova gravação | Substituir a abertura atual |
| 2. Escopo e quatro entregas | 45 s | Novo slide/narração | Substituir os dois primeiros slides |
| 3. Fluxo e arquitetura | 45 s | Reaproveitar + atualizar | Cortar repetições e acrescentar HTTP/FHIR |
| 4. Fisioterapia e relatório | 90 s | Regravar/reutilizar aplicação | Demonstrar limite, recálculo e relatório |
| 5. Voz e perfil acústico demonstrativo | 75 s | Reutilizar + complementar | Mostrar resultado, abstenção e limites |
| 6. Leito, cerca, fala e incidente | 105 s | Reaproveitar vídeo atual | Encadear somente a evidência útil |
| 7. Sinais, prescrição, evolução e FHIR | 75 s | Nova gravação | Mostrar fluxos atuais |
| 8. Testes, cobertura e limites | 45 s | Nova gravação | Apresentar resultados verificáveis |
| 9. Encerramento e próximos passos | 30 s | Nova gravação | Substituir a chamada final do YouTube |
| **Total** | **9 min** |  | Cerca de 9 minutos |

## Preparo antes da gravação

### Ambiente

- Use o Chrome ou Edge em **tela cheia**, sem favoritos, terminal ou explorador.
- Grave em 1920×1080 e 30 fps.
- Oculte o ponteiro enquanto não estiver apontando para uma ação.
- Aplique zoom do navegador suficiente para tornar botões e mensagens legíveis;
  não grave o aplicativo ocupando apenas uma parte pequena da tela.
- Feche mensagens, notificações e guias não relacionadas.
- Use somente mídia e textos marcados como **sintéticos/desidentificados**.
- Mantenha o terminal aberto em outro monitor, se necessário, mas não o inclua na
  gravação. Mostre apenas uma tela de confirmação da aplicação.
- Prepare previamente os arquivos de exemplo para evitar seleções no explorador.

### Áudio

- Normalize a fala final para aproximadamente **−14 LUFS** para publicação
  digital.
- Limite o pico verdadeiro a **−1 dBTP**.
- Remova ruído, cliques e respiração excessiva sem tornar a voz artificial.
- Não acelere a fala para compensar um roteiro longo; corte conteúdo repetido.
- Use música de fundo somente nos cortes, em volume muito baixo e sem competir
  com a voz.

### Estado inicial sugerido

Antes de iniciar a gravação:

1. Reinicie o backend e o frontend para limpar erros visuais transitórios.
2. Preserve apenas os registros sintéticos necessários para a demonstração.
3. Deixe preparados:
   - um vídeo sintético de fisioterapia;
   - um vídeo sintético de leito;
   - dois WAV sintéticos para comparação acústica;
   - `synthetic_vitals_24h.csv`;
   - `synthetic_prescriptions.json`;
   - `synthetic_clinical_note.json`;
   - identificador FHIR sintético aceito pelo servidor de demonstração.
4. Não exiba chaves, tokens, endpoints privados ou dados pessoais.
5. Confirme que o frontend e o backend correspondem ao commit que será citado
   na apresentação.

## Mapa de edição do vídeo atual

### Corte obrigatório

Remover integralmente:

- tela inicial prolongada com a frase “Inteligência Multimodal Clínica”;
- mensagens de terminal que ocupam meia tela;
- explorador de arquivos;
- espera pelo processamento;
- transições repetidas entre as mesmas telas;
- textos pequenos demais para leitura;
- afirmações que confundam inferência simulada com modelo validado;
- final “Dê um like e inscreva-se”.

### Aproximação por intervalo

| Intervalo atual | Ação de edição |
|---|---|
| 00:00–00:20 | Aproveitar no máximo 5–8 segundos da identidade visual. Substituir o título. |
| 00:20–01:40 | Descartar a maior parte. Regravar problema, escopo e limites em uma única fala. |
| 01:40–02:20 | Reaproveitar o slide de fluxo, cortando pausas e repetição. |
| 02:20–03:20 | Reaproveitar a arquitetura com novo texto sobre HTTP/FHIR e evidência sintética. |
| 03:20–06:30 | Substituir por gravação limpa da fisioterapia, mantendo somente trechos visuais úteis. |
| 06:30–08:20 | Aproveitar trechos do upload e da comparação de voz; acrescentar o resultado demonstrativo atual. |
| 08:20–09:00 | Cortar. |
| 09:00–11:20 | Reaproveitar como núcleo da demonstração de leito, com navegador em destaque. |
| 11:20–12:45 | Aproveitar apenas alerta, histórico e auditoria. Remover terminal e espera. |
| 12:45–12:57 | Cortar integralmente. |

## Roteiro detalhado

### Cena 1 — Abertura

**Duração:** 30 segundos  
**Imagem:** nova capa, seguida de corte direto para o apresentador ou para o
painel.  
**Aproveitamento:** apenas 5–8 segundos da identidade visual atual.

**Título recomendado:**

> **Vigia Saúde — Monitoramento multimodal para revisão humana**

**Fala pronta:**

> “Boa tarde. Este projeto apresenta o Vigia Saúde, um protótipo de apoio à
> revisão que reúne evidências de vídeo, fala e dados clínicos sintéticos em uma
> mesma linha temporal. A demonstração mostra o funcionamento integrado do
> software. Ela não apresenta um dispositivo clínico, diagnóstico automático ou
> atendimento de equipe médica validado.”

**Ação de montagem:**

- Entrada da capa com fade de 0,3 s.
- Exibir o subtítulo “Protótipo acadêmico · dados e integrações sintéticos”.
- Fazer corte para o slide de escopo no fim da frase.

### Cena 2 — Problema, objetivo e escopo

**Duração:** 45 segundos  
**Imagem:** quatro cartões limpos: imagem, voz, dados clínicos e alertas.  
**Ação no vídeo atual:** substituir o trecho de 00:20–01:40.

**Conteúdo dos cartões:**

1. **Imagem:** YOLO Pose, cerca virtual e regras geométricas.
2. **Voz:** Azure Speech, regras de menções e comparação acústica exploratória.
3. **Dados clínicos:** sinais, prescrições, HTTP, FHIR e evolução textual sintética.
4. **Saída:** evidências temporais, eventos, histórico e webhook de teste.

**Fala pronta:**

> “O problema não é apenas coletar dados, mas torná-los auditáveis e
> relacionáveis no tempo sem transformar uma coincidência em diagnóstico. No
> módulo de imagem, o protótipo calcula pose, cercas e desvios geométricos. Na
> voz, combina transcrição, menções textuais e descritores acústicos
> exploratórios. Nos dados clínicos, identifica anomalias demonstrativas e
> compara prescrições com uma referência fornecida. O resultado é um conjunto
> de evidências para revisão humana, e não uma conclusão clínica automática.”

**Operação no sistema:** nenhuma. Essa cena é de slides.

### Cena 3 — Fluxo e arquitetura

**Duração:** 45 segundos  
**Imagem:** reutilizar o fluxo de 01:40–02:20 e a arquitetura de 02:20–03:20.  
**Ação de edição:** atualizar os textos, reduzir para uma única passagem pelos
componentes e remover o zoom excessivo em caixas pequenas.

**Fala pronta:**

> “Vídeo e áudio entram por gravação ou sessão de câmera. O backend local usa
> FFmpeg e YOLOv8 Pose no caminho visual. O caminho de fala usa Azure Speech em
> português, regras locais e Azure AI Language opcionalmente. Os eventos recebem
> timestamps e são correlacionados dentro da mesma sessão, em uma janela de até
> dez segundos. Sinais e prescrições podem entrar por HTTP ou FHIR autenticado.
> O histórico fica em SQLite, e o webhook demonstrativo confirma apenas a
> entrega a um receptor local, sem comprovar leitura ou atendimento.”

**Texto obrigatório na tela:**

> “Correlação temporal ≠ identidade do paciente ≠ causalidade”

**Ação de montagem:**

- Mostrar cada componente por 5–8 segundos.
- Dar destaque visual ao caminho vídeo/fala → correlação → revisão.
- Não ler todos os nomes técnicos simultaneamente.

### Cena 4 — Fisioterapia

**Duração:** 1 minuto e 30 segundos  
**Imagem:** gravação nova, limpa e com o navegador maximizado.  
**Aproveitamento:** usar apenas o trecho atual em que os keypoints e métricas
estão claramente visíveis.

**Fala pronta:**

> “Agora vou demonstrar a fisioterapia. A postura do exercício foi informada
> como em pé, e o limite do joelho é configurado para este exemplo sintético.
> O valor de 150 graus serve apenas para tornar o desvio mensurável; não é uma
> faixa clínica. Ao salvar, a aplicação recalcula os eventos. Em seguida, o
> relatório mostra o mesmo limite, o aviso de não diagnóstico e o evento
> geométrico detectado.”

**Operação exata no sistema:**

1. Abra `/video`.
2. Se o vídeo já estiver preparado, selecione diretamente o item de fisioterapia.
   Não grave novamente a seleção do arquivo.
3. Confirme visualmente o título
   **“Análise de vídeos de fisioterapia”**.
4. No painel **Regras de alerta configuráveis**, localize:
   **“Limite do ângulo interno do joelho em graus”**.
5. Substitua o valor por **150**.
6. Pare o ponteiro por um instante para que o valor possa ser lido.
7. Clique em **Salvar limites e recalcular**.
8. Aguarde o botão voltar ao estado habilitado.
9. Mostre o evento gerado no painel.
10. Clique em **↓ Baixar relatório**.
11. Abra o JSON baixado por 3–5 segundos ou prepare uma versão ampliada em
    seguida, destacando:
    - `"mode": "fisio"`;
    - `"knee_angle": 150`;
    - o evento `Ângulo interno do joelho < 150°`;
    - o campo de aviso/disclaimer.

**Cortes recomendados nesta cena:**

- O upload completo, se o vídeo já estiver na biblioteca.
- Espera durante análise.
- Terminal.
- Rolagem longa pelo relatório.
- Demais limites que não serão explicados.

**Enquadramento sugerido:**

- Primeiro plano com vídeo + keypoints por 20–30 segundos.
- Segundo plano com a configuração de limite por 15 segundos.
- Terceiro plano com relatório ampliado por 10–15 segundos.

### Cena 5 — Voz e perfil acústico demonstrativo

**Duração:** 1 minuto e 15 segundos  
**Imagem:** upload preparado de áudio de referência e corrente, resultado e
comparação.  
**Aproveitamento:** reutilizar partes de 06:30–08:20, excluindo upload longo e
espera.

**Fala pronta — parte 1, transcrição:**

> “No módulo de voz, a primeira evidência é a transcrição produzida pelo
> Speech. As regras locais verificam termos e tentativa de negação. Isso pode
> destacar uma frase como ‘estou com falta de ar’, mas essa menção vem do texto
> reconhecido e não prova uma alteração acústica da voz.”

**Operação exata — transcrição:**

1. Abra `/voice`.
2. Marque **Confirmo autorização para processar o áudio**.
3. Importe primeiro a gravação de referência.
4. Aguarde **Análise concluída**.
5. Importe a gravação corrente.
6. Mostre:
   - o alerta de simulação;
   - a transcrição;
   - a prioridade de revisão, quando aplicável;
   - o aviso de que os arquivos usados são tons, não fala, se esse for o caso.

**Fala pronta — parte 2, perfil acústico:**

> “A comparação usa somente os descritores medidos nas duas gravações: pitch,
> variação do pitch, energia e cruzamentos por zero. Para o caso demonstrativo,
> o resultado informa um perfil acústico artificial ou se abstém quando falta
> fala suficiente. Esses rótulos não representam fadiga, disartria, dificuldade
> respiratória nem diagnóstico.”

**Operação exata — comparação:**

1. Abra o detalhe **Indicadores acústicos exploratórios**.
2. Em **Gravação de referência**, escolha a primeira gravação.
3. Clique em **Comparar características da fala**.
4. Mostre as porcentagens/diferenças.
5. Mostre **Detector acústico demonstrativo**.
6. Enfatize o aviso final do componente.
7. Não use expressões como “paciente cansado”, “voz disártrica” ou
   “dificuldade respiratória detectada”.

**Texto obrigatório na tela:**

> “Perfil acústico artificial — não é uma classe clínica”

### Cena 6 — Leito, cerca, fala e incidente multimodal

**Duração:** 1 minuto e 45 segundos  
**Imagem:** reaproveitar o trecho de 09:00–11:20, sem terminal e com zoom.  
**Objetivo:** demonstrar o núcleo multimodal da solução.

**Fala pronta:**

> “Neste módulo de leito, uma saída da cerca gera evidência visual. Em seguida,
> uma fala reconhecida próxima no tempo gera uma segunda evidência. Como ambas
> pertencem à mesma sessão e estão dentro da janela temporal, a aplicação as
> apresenta em um incidente multimodal. Essa associação não identifica a pessoa,
> não demonstra causalidade e não comprova queda ou emergência.”

**Operação exata no sistema:**

1. Abra `/telemetry`.
2. Selecione o vídeo sintético já processado.
3. Reproduza do início.
4. Mostre simultaneamente:
   - vídeo;
   - cerca virtual;
   - evento visual;
   - transcrição;
   - alerta.
5. Pause quando o incidente **Imagem + fala** estiver legível.
6. Aponte para as evidências e seus horários.
7. Clique em **Atualizar notificações** somente se a entrega ao receptor estiver
   preparada.
8. Mostre **Aceita pelo destino**.
9. Clique em **Ir ao atendimento**.
10. Diga imediatamente:
    > “Este botão registra uma intenção; não confirma deslocamento ou atendimento.”
11. Clique em **Consultar / atualizar histórico unificado**.
12. Expanda o incidente.
13. Clique em **Consultar alterações e evidências anteriores**.
14. Mostre o histórico por 5–8 segundos.

**Não mostrar ou encerrar rapidamente:**

- armazenamento em terminal;
- colunas de log irrelevantes;
- espera longa por notificação;
- tela com campos muito pequenos.

### Cena 7 — Sinais, prescrições, evolução e FHIR

**Duração:** 1 minuto e 15 segundos  
**Imagem:** gravação nova em tela cheia.  
**Objetivo:** mostrar as três pendências recentemente implementadas além da
demonstração fixa anterior.

#### Parte A — Simulador sintético e evolução de notas (45 segundos)

**Preparação:**

- Inicie previamente uma sessão sintética de câmera ou replay, sem mostrar os
  passos de permissão.
- Posicione a página para que o componente **Simulação sintética vinculada à
  sessão** apareça inteiro.

**Fala pronta:**

> “O simulador vinculado à sessão gera sinais e uma prescrição de demonstração.
> Nesta versão, a nota sintética também pode ser alterada entre amostras. O
> texto não é persistido; o sistema guarda somente menções derivadas e suas
> transições. Assim, podemos ver uma menção introduzida, mantida e depois
> resolvida sem alegar evolução clínica real.”

**Operação exata:**

1. No campo **Nota sintética opcional para a próxima amostra**, escreva:
   `Pessoa sintética relata cansaço.`
2. Deixe a sessão avançar ou inicie **Iniciar simulador de sinais e prescrição**.
3. Aguarde a nova amostra.
4. Mostre **introduzidas: cansaço**.
5. Substitua o campo por:
   `Pessoa sintética relata cansaço, sem falta de ar.`
6. Aguarde outra amostra e mostre **mantidas: cansaço**.
7. Substitua o campo por:
   `Pessoa sintética relata bem-estar.`
8. Aguarde a última amostra e mostre **resolvidas: cansaço**.
9. Mostre a frase **O texto original não foi persistido**.

Se o intervalo de gravação for insuficiente, grave as três amostras em cortes
separados e una-as com três legendas: “Introdução”, “Persistência” e
“Resolução”.

**Dado clínico mínimo a exibir:**

- FC: **132 bpm**;
- SpO₂: **88%**;
- prescrição observada: **30 mg**;
- referência sintética: **10 mg**.

#### Parte B — FHIR e entrega local (30 segundos)

Se o objetivo for mostrar consulta FHIR manual:

1. Abra o painel **Séries, prescrições e texto clínico**.
2. Em **Consulta autorizada a prontuário FHIR R4**, informe o identificador
   sintético preparado.
3. Marque **Confirmo autorização para consultar este prontuário e importar
   seus dados**.
4. Clique em **Consultar FHIR**.
5. Abra o resultado e mostre os dados sintéticos.

Se o objetivo for mostrar a ingestão contínua HTTP/FHIR vinculada a uma sessão,
não tente digitar manualmente payloads ou tokens na aplicação. Prepare antes:

- uma sessão ativa;
- um Bundle FHIR sintético;
- um script ou ferramenta de testes que já envie o payload autenticado;
- a tela da sessão pronta para exibir o resultado.

Grave somente o resultado:

- correspondência temporal na mesma sessão;
- FC ou prescrição recebida;
- evento de revisão;
- status **Aceito pelo destino**.

**Fala pronta:**

> “O fluxo HTTP/FHIR recebe dados somente com token e dentro de uma sessão.
> Neste caso, o servidor e o receptor são locais e sintéticos. A resposta
> ‘Aceito pelo destino’ confirma apenas a entrega técnica; não confirma
> identidade do paciente, comunicação com uma equipe nem atendimento.”

### Cena 8 — Testes, cobertura e limites

**Duração:** 45 segundos  
**Imagem:** slide simples com quatro números grandes e uma coluna de limites.  
**Ação:** nova gravação; não mostrar GitHub Actions por muito tempo.

**Números da versão validada:**

- 415 testes backend;
- 131 testes Angular;
- 4 testes AudioWorklet;
- 6 de 6 cenários E2E;
- cobertura backend: aproximadamente 94% de linhas e 89% de branches;
- cobertura frontend: aproximadamente 93% de linhas e 84% de branches.

Antes da gravação final, confirme novamente os números no commit que será
entregue. Se houver diferença, atualize o slide; não mantenha contagem antiga.

**Fala pronta:**

> “A versão demonstrada passou por 415 testes backend, 131 testes Angular, quatro
> testes do AudioWorklet e seis cenários E2E. Os gates também mantêm cobertura
> acima dos mínimos do projeto. Esses testes comprovam integração, contratos,
> regressões e interfaces do software; não provam acurácia de um modelo clínico
> nem segurança para uso hospitalar.”

**Limites obrigatórios no slide:**

- sem classificação clínica validada de fadiga, disartria ou dificuldade
  respiratória;
- mídia, respostas Speech/Language e integrações automatizadas podem ser
  simuladas nos testes;
- sem sensores ou prontuário institucional reais verificados;
- sem identidade clínica entre importações independentes;
- sem destino de equipe real nem confirmação de atendimento;
- não expor ou usar com dados reais sem autenticação geral, autorização,
  transporte seguro e governança.

### Cena 9 — Encerramento e próximos passos

**Duração:** 30 segundos  
**Imagem:** slide final com contribuição e três próximos passos.  
**Ação:** substituir a tela final do YouTube.

**Próximos passos no slide:**

1. Validar modelos e regras com dados autorizados e rotulados.
2. Integrar fontes e destinos institucionais reais.
3. Implementar segurança, governança e avaliação operacional.

**Fala pronta:**

> “A contribuição do protótipo é demonstrar uma arquitetura multimodal
> verificável, com correlação temporal, rastreabilidade e revisão humana.
> Fisioterapia, voz demonstrativa, sinais, prescrições, evolução sintética,
> histórico e alertas estão integrados no software. O próximo nível exige
> validação clínica, integração institucional, governança e controles de
> segurança. Obrigado.”

**Texto final opcional no último quadro:**

> “Vigia Saúde · Protótipo acadêmico para revisão humana”

## Ordem de gravação recomendada

Gravar fora da ordem final reduz erros e repetição:

1. Cena 4 — fisioterapia.
2. Cena 5 — voz.
3. Cena 6 — leito e incidente.
4. Cena 7 — evolução e FHIR.
5. Cenas 1, 2 e 9 — apresentador e slides.
6. Cenas 3 e 8 — explicar arquitetura e resultados.

## Plano de pós-produção

1. Sincronize áudio e vídeo.
2. Corte silêncios de mais de 1 segundo que não ajudem a leitura da interface.
3. Faça zoom eletrônico somente em áreas estáveis; evite zoom durante o clique.
4. Adicione retângulos ou realce discreto ao botão ou resultado relevante.
5. Legende termos técnicos e avisos.
6. Insira um rótulo fixo **SIMULAÇÃO SINTÉTICA** durante testes e interfaces
   demonstrativas.
7. Não deixe resultados diferentes do roteiro por mais de dois segundos sem
   explicação.
8. Normalize o áudio e faça revisão em fone e caixa de som de notebook.
9. Verifique o vídeo completo em tela de projeção ou televisão.
10. Confirme que nenhuma chave, token, identificador real, endpoint privado ou
    dado pessoal aparece.

## Checklist final de aceite

- [ ] Duração entre 9 e 10 minutos.
- [ ] Capa não chama o produto de sistema clínico validado.
- [ ] Não há terminal, explorador ou espera longa visível.
- [ ] Fisioterapia mostra limite, recálculo e relatório.
- [ ] Voz distingue texto, acústica exploratória e condição clínica.
- [ ] Perfil acústico demonstrativo é apresentado como artificial.
- [ ] Leito mostra evento, fala, incidente e histórico.
- [ ] Evolução mostra introdução, persistência e resolução.
- [ ] Texto original da nota não é apresentado como persistido.
- [ ] FHIR/webhook são identificados como locais e sintéticos.
- [ ] “Ir ao atendimento” não é narrado como atendimento concluído.
- [ ] Testes são apresentados como validação de software, não clínica.
- [ ] Contagens e cobertura correspondem ao commit final.
- [ ] Limites e próximos passos aparecem explicitamente.
- [ ] Encerramento acadêmico substitui a chamada de YouTube.
- [ ] Nenhum dado ou segredo real está visível.

## Linguagem a evitar

Evite:

- “detectamos fadiga na voz”;
- “detectamos disartria”;
- “identificamos dificuldade respiratória”;
- “diagnóstico automático”;
- “paciente caiu”;
- “o sistema notificou a equipe”;
- “o webhook confirma que alguém atendeu”;
- “integração com o prontuário do hospital”;
- “IA clinicamente validada”.

Prefira:

- “a aplicação sinalizou”;
- “evento geométrico para revisão”;
- “menção textual reconhecida”;
- “perfil acústico artificial”;
- “correlação temporal”;
- “receptor sintético local”;
- “aceito pelo destino técnico”;
- “protótipo para revisão humana”.
