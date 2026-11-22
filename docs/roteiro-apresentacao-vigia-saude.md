# Avaliação e roteiro da apresentação — Vigia Saúde

## Parecer executivo

A [apresentação revisada](./Vigia-Saude-apresentacao-revisada.pptx) foi recriada
em 16:9 com textos e formas editáveis, corrigindo as alegações do arquivo
original, que foi preservado. Os seis slides apresentam escopo, fluxo,
arquitetura, resultados, limitações e próximos passos. A gravação existente não
foi atualizada nesta revisão e deve ser conferida antes da entrega.

Não apresente a menção textual a “cansaço” como detecção acústica de fadiga,
nem os descritores de voz como classificação de disartria. Os cartões de
telemetria são fictícios. A API autenticada para ingestão HTTP/FHIR e o webhook
opcional foram exercitados localmente com conteúdo/serviços sintéticos; ainda
faltam fontes e destinatários institucionais autorizados. Os testes não
demonstram acurácia ou segurança clínica. O `GET` do fluxo clínico ainda não
tem autenticação de usuário, portanto não use dados reais nem exponha a
aplicação em rede não confiável.

> **Precisão sobre a enfermaria:** o painel pode ser acompanhado por uma equipe;
> quando configurado, o webhook envia um aviso genérico de alertas críticos
> confirmados. Ainda não há destinatário de equipe real verificado, nem garantia
> de leitura ou atendimento. “Ir ao atendimento” registra apenas uma intenção.

## Sequência recomendada e cronograma

| Tempo | Slide / trecho | Ação |
|---|---|---|
| 0:00–0:25 | 1 — Abertura | Apresentar nome e objetivo, sem prolongar a capa |
| 0:25–1:30 | 2 — Problema e escopo | Explicar o problema e dizer o que o protótipo realmente faz |
| 1:30–2:20 | 3 — Fluxo de uso | Apresentar entradas, análise, correlação e revisão humana |
| 2:20–3:20 | 4 — Arquitetura | Localizar YOLO, Azure Speech, regras, Azure Language opcional e SQLite |
| 3:20–9:20 | Demonstração gravada | Vídeo/áudio, anomalia, alerta, ação registrada e histórico |
| 9:20–10:30 | 4 — Decisões técnicas | Explicar regras, timestamps e janela de correlação |
| 10:30–11:30 | 5 — Testes, resultados e limites atuais | Distinguir teste de software de validação do modelo |
| 11:30–14:00 | 6 — Melhorias futuras | Apresentar as quatro frentes como roadmap, não como recursos atuais |
| 14:00–15:00 | Encerramento | Reforçar contribuição e finalizar |

O cronograma soma 15 minutos. Faça ensaios cronometrados; se a gravação passar de seis minutos, reduza explicações repetidas nos slides, não acelere a fala.

## Falas sugeridas

### 0:00–0:25 — Slide 1: abertura

> “Boa tarde. Este trabalho apresenta o Vigia Saúde, um protótipo de monitoramento multimodal. Vou mostrar como vídeo e fala podem gerar evidências temporais para revisão humana e demonstrar o fluxo na aplicação. Também vou delimitar o que foi implementado e o que ainda precisa de validação.”

A capa revisada apresenta **“Vigia Saúde — Monitoramento multimodal para revisão humana”**. Evite “inteligência multimodal clínica” se isso sugerir diagnóstico ou fusão clínica validada.

### 0:25–1:30 — Slide 2: problema e escopo

Apresente os quatro cartões do slide como capacidades efetivamente implementadas e seus limites:

- Entradas: vídeo gravado ou câmera; áudio associado à sessão.
- Imagem: pose e regras geométricas/cerca virtual.
- Fala: transcrição em português e regras locais de menções.
- Resultado: alerta e evidências para revisão humana.

**Fala:**

> “O desafio é reunir evidências sem tratar um evento isolado como diagnóstico. Neste protótipo, a imagem é analisada por pose e regras de movimento; a fala é transcrita pelo Azure Speech e examinada por regras locais. Uma menção textual a ‘cansaço’ ou ‘fadiga’ pode gerar um aviso, mas isso não é detecção vocal de fadiga. Há importação manual CSV/JSON e APIs autenticadas para receber amostras HTTP e Bundles FHIR R4 em uma sessão ativa; foram exercitadas localmente com dados sintéticos, sem prontuário institucional ou sensores conectados. Não há classificador validado de fadiga/disartria nem verificação de dose ou interações.”

### 1:30–2:20 — Slide 3: fluxo do sistema

Apresente os quatro passos do slide: entradas, análise, correlação e revisão.
Prefira “processamento local + serviços Azure” a “IA híbrida” sem explicação.

**Fala:**

> “O fluxo começa com vídeo e áudio de uma sessão. As duas modalidades são processadas separadamente; as evidências recebem referências temporais e podem ser correlacionadas. Se habilitado e configurado, um webhook envia um aviso genérico para um destino externo, sem comprovar que uma equipe recebeu ou atendeu. O profissional continua responsável pela interpretação e pela decisão.”

### 2:20–3:20 — Slide 4: arquitetura

O slide separa o backend local dos serviços externos opcionais. Relacione os
componentes aos quatro passos do slide anterior: entrada → vídeo local →
fala/Azure → correlação → histórico → painel.

**Fala:**

> “No caminho da imagem, o backend local executa YOLOv8 Pose e aplica regras geométricas, incluindo a cerca virtual. No caminho de fala, o Azure Speech faz reconhecimento em português e regras locais identificam menções relevantes. Azure AI Language é uma integração opcional para texto, sentimento e termos-chave; ela não é necessária para o alerta demonstrado. A correlação de incidentes ocorre na aplicação, com janela de até dez segundos na mesma sessão, e o histórico fica em SQLite local.
>
> O painel também aceita importação manual de séries e prescrições, consulta FHIR autorizada e nota textual enviada ao Azure AI Language com autorização explícita. Esses dados são separados dos incidentes de vídeo/áudio; FHIR foi testado com servidor sintético e não há sensores conectados. A telemetria demonstrativa continua sendo fictícia.”

**Atualização para a versão atual:** a observação de que as importações estão
separadas dos incidentes aplica-se à importação manual. A ingestão contínua
HTTP/FHIR associa amostras à mesma sessão de mídia e à linha temporal, sem
inferir identidade ou causalidade. O webhook pode enfileirar eventos genéricos
dessa ingestão, mas ainda não existe destino institucional verificado.

**Transição para o vídeo:**

> “Com a arquitetura em mente, vou mostrar o fluxo funcionando: da reprodução e reconhecimento até o alerta e o histórico.”

### 3:20–9:20 — Demonstração gravada da aplicação

Grave uma sessão contínua ou edite com transições discretas e identificáveis. Prefira uma gravação de leito com uma saída da cerca e uma fala crítica próximas no tempo. Use mídia autorizada e sem dados pessoais; identifique claramente material sintético. Se o sistema estiver usando mocks, diga isso na tela ou na narração.

| Tempo | Mostrar | Narração |
|---|---|---|
| 3:20–3:50 | Abrir o módulo de leito e explicar a fonte | “Esta é uma sessão de demonstração preparada. A aplicação pode analisar gravação reproduzida; o fluxo de câmera exige início explícito e permissões.” |
| 3:50–4:30 | Selecionar/importar o vídeo e conferir a cerca | “A cerca virtual é uma regra configurada para a sessão. Cruzá-la produz uma evidência de imagem; não prova queda ou emergência.” |
| 4:30–6:00 | Reproduzir; mostrar vídeo, status de análise e transcrição | “O vídeo é analisado pelo backend local. O áudio da reprodução segue ao Azure Speech para transcrição em português. Vou destacar a transcrição e o evento com seus horários.” |
| 6:00–7:10 | Mostrar alerta visual e menção de fala | “Cada evidência pode gerar alerta individual. Quando uma saída da cerca e uma fala crítica ocorrem na mesma sessão dentro da janela temporal, o sistema pode reuni-las.” |
| 7:10–8:00 | Mostrar incidente unificado e evidências | “Aqui vemos o incidente e as evidências que o compõem. A correlação é temporal; não identifica o falante nem comprova que a fala foi causada pelo movimento.” |
| 8:00–8:20 | Mostrar o dashboard e acionar “Ir ao atendimento” | “Essa ação registra uma intenção, não confirma atendimento. Um webhook opcional é disparado pelo alerta confirmado, não pelo botão; o destino real da equipe ainda não foi verificado.” |
| 8:20–8:45 | Abrir o histórico unificado | “O histórico permite consultar incidentes de mídia e suas alterações após a sessão. Não é um prontuário.” |
| 8:45–9:20 | Mostrar um Bundle FHIR sintético recebido na sessão de câmera, a correspondência temporal e o status do webhook local | “Este sinal vital é sintético e foi associado ao horário da sessão, não à identidade de uma pessoa. O evento genérico chegou ao receptor de teste; isso não comprova comunicação com uma equipe. A ingestão usa token e ainda não há fonte FHIR ou destinatário institucional verificados.” |

O vídeo publicado ainda não foi atualizado para demonstrar a ingestão contínua
FHIR, o mapeamento temporal nem o status do webhook clínico. Regrave esse
trecho antes de afirmar que o vídeo comprova o fluxo atualizado. O backend E2E
comprova somente a integração local com FHIR e webhook sintéticos.

**Demonstração de Azure:** Speech e Language responderam a áudio e texto sintéticos em uma verificação pontual. Antes da gravação, confirme novamente conectividade e credenciais sem exibir chaves ou endpoints privados. Uma execução simulada não deve ser apresentada como chamada Azure real.

**Se usar a câmera ao vivo:** mostre que a prévia é local, configure e salve a cerca, então inicie explicitamente câmera e microfone. Não chame o fluxo de vídeo gravado de câmera ao vivo. A captura pode ter latência e perder movimentos entre amostras.

### 9:20–10:30 — Slide 4: interpretação técnica

> “A detecção visual combina keypoints do YOLOv8 Pose com regras geométricas; não é um classificador clínico de quedas. O Azure Speech transforma a fala em texto. Regras locais identificam menções como ‘cansaço’ ou ‘fadiga’ e podem gerar avisos; isso identifica as palavras reconhecidas, não sinais acústicos de fadiga. A disartria também não é classificada pela implementação: seria necessário um modelo específico, avaliado e validado para esse objetivo. O incidente multimodal usa timestamps e uma janela de até dez segundos na mesma sessão. Isso organiza evidências, mas não demonstra identidade, causalidade ou diagnóstico.”

**Atualização técnica:** a interface inclui comparação acústica exploratória
entre uma gravação e uma referência escolhida pelo operador (pitch, energia e
cruzamentos por zero em segmentos reconhecidos como fala). Ela não identifica
fadiga ou disartria, e diferenças podem refletir conteúdo, microfone ou ruído.
A ingestão contínua HTTP/FHIR é exercitada em E2E com uma sessão de câmera
sintética: no caso de câmera, `effectiveDateTime` usa `started_at`; na
reprodução, o produtor precisa informar `session_origin_at` correspondente ao
início temporal do vídeo. A câmera fixa essa origem no horário definido pelo
backend; eventos anteriores à origem são rejeitados mesmo com deslocamento de
reprodução. Cada Bundle é aceito integralmente ou revertido. O evento tem
correspondência de tempo/mídia e gera entrega ao webhook sintético. A comparação
acústica continua experimental, sem classificador ou validação clínica, e o
vídeo publicado ainda não demonstra o fluxo FHIR atualizado.

### 10:30–11:30 — Slide 5: resultados e limites atuais

Use o slide para resumir testes de software e limites atuais. Deixe as melhorias futuras para o slide 6. Não use métricas de acurácia clínica: os testes E2E usam reconhecimento e inferência simulados.

**Fala:**

> “Os testes E2E documentados percorrem os principais fluxos da aplicação, incluindo alertas, correlação, histórico e importação dos exemplos clínicos sintéticos. A validação local atual teve seis de seis testes E2E, 382 testes backend, 119 testes Angular e quatro testes AudioWorklet aprovados. No E2E de câmera, a ingestão FHIR e o webhook usam dados e serviços locais sintéticos; YOLO e Speech também são simulados. Isso demonstra o funcionamento integrado do software, não a precisão dos modelos nem a eficácia clínica.
>
> Os resultados também dependem do enquadramento, iluminação, oclusão, qualidade do áudio e contexto da fala. As importações são manuais, pseudonimizadas e separadas dos incidentes de mídia; não há sensores ou prontuário institucional verificados. O webhook opcional não comprova que alguém recebeu ou atendeu o alerta.”

**Transição para o roadmap:**

> “Com esses limites claros, o próximo slide mostra o que precisaria ser desenvolvido e validado antes de considerar uma implantação hospitalar.”

### 11:30–14:00 — Slide 6: melhorias futuras

O slide revisado apresenta quatro frentes futuras: validação, integração de
fontes reais, operação dos alertas e governança. O conector FHIR e o webhook já
existem como protótipos, mas ainda dependem de sistemas reais e validação.
O prompt abaixo é apenas uma alternativa visual, não uma etapa necessária.

#### Prompt para o Gemini

> Crie uma ilustração conceitual para um slide acadêmico de pós-graduação em tecnologia, horizontal 16:9, com fundo branco ou muito claro e estilo vetorial corporativo, elegante e simples. Use a identidade visual de tecnologia em saúde: azul-marinho, azul-petróleo, verde-água e pequenos acentos em ciano; ícones e personagens discretos, traços limpos, bom contraste e espaço negativo. A imagem deve ser legível projetada em uma sala.
>
> Componha quatro cenas ou cartões visuais claramente separados, alinhados da esquerda para a direita como uma jornada de evolução futura. Use apenas ilustrações e ícones; **não inclua palavras, letras, números, logotipos, siglas, rótulos ou texto legível**. Deixe uma faixa livre acima ou abaixo de cada cartão para que eu adicione os títulos no PowerPoint.
>
> 1. **Validação e evidência:** equipe multidisciplinar revisando, de forma ética, dados de áudio e vídeo desidentificados, com anotações e gráficos de avaliação; represente análise de qualidade, falsos positivos e validação, sem sugerir resultados já obtidos.
> 2. **Integração clínica autorizada:** fontes de dados hospitalares, como monitor de sinais e prontuário eletrônico, conectando-se por um fluxo seguro e padronizado a uma plataforma; represente como possibilidade futura, não como integração já existente.
> 3. **Fluxo operacional da enfermagem:** profissional de enfermagem acompanhando um dashboard e recebendo visualmente um alerta com opções de revisar, confirmar e encaminhar; deixe claro pela cena que há supervisão humana. Não represente uma notificação já implantada ou atendimento automático.
> 4. **Privacidade, segurança e governança:** dados protegidos por escudo e chave, acessos controlados e trilha de auditoria, com a equipe definindo consentimento, retenção e responsabilidades.
>
> As quatro cenas devem parecer uma proposta de roadmap, não uma implantação operacional. Use separadores discretos. Evite imagens de pacientes identificáveis, diagnósticos, promessas de prevenção de quedas, classificações automáticas de fadiga/disartria ou resultados numéricos. Não represente FHIR ou webhook como integrações institucionais já verificadas. Preserve áreas limpas para os títulos “Validar”, “Integrar”, “Operacionalizar” e “Governar”.

#### Títulos para uma ilustração alternativa

1. **Validar com evidências**
2. **Integrar sensores e prontuário**
3. **Operacionalizar alertas**
4. **Proteger e governar dados**

Em fonte menor, use **“Roadmap para validação e integração reais”**. O conector FHIR e o webhook já são protótipos; sua operação institucional continua pendente.

#### Falas para acompanhar cada frente

**Introdução do slide — 10 a 15 segundos**

> “Estas quatro frentes mostram o caminho para sair de um protótipo funcional e chegar a uma solução avaliável e integrada com segurança. O código FHIR e o webhook existem, mas as integrações reais ainda não foram verificadas.”

**1. Validar com evidências — cerca de 25 segundos**

> “Primeiro, precisamos avaliar os componentes com dados autorizados e desidentificados, rótulos independentes e métricas claras de acerto, falso positivo, falso negativo e latência. Só depois de uma avaliação reproduzível e validação clínica faria sentido discutir o uso de novos classificadores. Azure Speech transcrever a fala, por si só, não identifica disartria nem fadiga vocal.”

**2. Integrar dados clínicos — cerca de 25 segundos**

> “A segunda frente é integrar fontes reais, como sinais de equipamentos e sistemas hospitalares, usando autorização institucional. Os cartões são fictícios; o conector FHIR foi testado apenas com servidor sintético e não há sensor conectado.”

**3. Operacionalizar alertas — cerca de 25 segundos**

> “A terceira frente é acordar com a enfermagem quem acompanha, recebe e escala cada alerta. O webhook opcional envia mensagem genérica e foi testado localmente; ainda não foi conectado a profissionais identificados.”

**4. Proteger e governar dados — cerca de 25 segundos**

> “Por fim, uma implantação exigiria políticas institucionais de consentimento, acesso por função, proteção dos dados, retenção, auditoria e resposta a incidentes. Segurança e privacidade precisam ser requisitos do desenho e verificados antes de qualquer piloto, não apenas uma característica visual do sistema.”

**Fecho do roadmap — cerca de 10 segundos**

> “Essas frentes dependem umas das outras: primeiro evidência e validação, depois integração e operação controlada, sempre com governança e supervisão humana.”

### 14:00–15:00 — Encerramento

> “Em síntese, o Vigia Saúde demonstra como evidências de imagem e fala podem ser processadas por componentes distintos, relacionadas no tempo e apresentadas em um histórico para revisão humana. O roadmap deixa claro que validação, integração hospitalar, operação de alertas e governança são etapas futuras. O valor desta entrega é tornar o fluxo técnico concreto e auditável, sem confundir uma demonstração de software com um dispositivo clínico validado. Obrigado.”

## Checklist antes de gravar

- [x] Recriar os slides editáveis em 16:9 sem alegações clínicas não comprovadas.
- [x] Apresentar limites e próximos passos, distinguindo protótipos de integrações reais.
- [ ] Conferir e, se necessário, atualizar a gravação da aplicação após as alterações.
- [ ] Confirmar se Azure Speech e, se mostrado, Azure AI Language estão realmente ativos; distinguir isso de mocks.
- [ ] Garantir que o exemplo mostre áudio, vídeo, timestamps, alerta, correlação e histórico.
- [ ] Explicar que o webhook opcional não garante contato com a equipe e que “Ir ao atendimento” registra apenas uma intenção.
- [ ] Usar mídia autorizada e desidentificada; ocultar credenciais, dados pessoais e informações sensíveis.
- [ ] Ensaiar a apresentação completa com cronômetro e manter a duração total em até 15 minutos.
- [ ] Publicar no YouTube ou Vimeo como público ou não listado e testar o link antes da entrega.

## Referências do projeto

- [Relatório técnico multimodal](./relatorio-tecnico-multimodal.md)
- [README do projeto](../README.md)
