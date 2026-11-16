# Avaliação e roteiro da apresentação — Vigia Saúde

## Parecer executivo

A apresentação tem uma identidade visual consistente e inclui um diagrama de arquitetura que ajuda a entender os fluxos local e Azure. Porém, **a versão atual ainda não está pronta para gravação**: um slide atribui capacidades que não existem na aplicação, outro promete apoio clínico “em tempo real”, e o último está praticamente vazio. Além disso, a apresentação não mostra a interface nem resultados verificáveis.

As correções mais importantes são:

1. **Substituir o conteúdo do slide 2.** Ele cita cirurgia, detecção vocal de fadiga/disartria, lentidão, confusão, monitoramento de sinais vitais em tempo real, interação medicamentosa e deterioração clínica. Essas funções não são implementadas dessa forma. A telemetria disponível é fictícia; Azure Speech transcreve a fala e regras locais podem sinalizar a menção textual a “cansaço” ou “fadiga” como aviso. Isso não equivale a detectar fadiga pela voz. Não há classificador de disartria.
2. **Revisar as promessas do slide 1.** Trocar “apoio à decisão clínica proativa” por “apoio à revisão humana” e “segurança de dados” por uma descrição factual, como “processamento local e integração demonstrativa com Azure”. A implementação não comprova uma certificação ou garantia de segurança clínica.
3. **Ajustar o slide 3.** A sequência coleta → análise → correlação → revisão humana é útil, mas substituir “em tempo real” por “durante a sessão” ou “fluxo de monitoramento demonstrativo”. Não há garantia de latência clínica ou análise contínua de todas as fontes.
4. **Manter e simplificar o slide 4.** O diagrama representa bem YOLOv8 Pose local, Azure Speech, regras de fala, correlação temporal, SQLite e painel. Distinguir gravação reproduzida de câmera/microfone e deixar explícito que Azure AI Language é opcional.
5. **Preencher o slide 5.** Usá-lo para resultados de software, limitações e próximos passos. Evitar métricas de acurácia clínica: os testes E2E usam reconhecimento e inferência simulados.
6. **Adicionar a gravação da aplicação** entre a arquitetura e o fechamento, idealmente como vídeo inserido no PowerPoint ou como captura de tela narrada.
7. **Rever o formato.** O arquivo está configurado em 4:3, enquanto as imagens principais são 16:9. Padronizar o deck em 16:9 ou conferir o enquadramento de cada slide no modo de apresentação.

As imagens contêm textos incorporados, não editáveis como texto do PowerPoint. Recomenda-se recriar especialmente os slides 1–3 com formas e textos editáveis, para corrigir alegações e melhorar a leitura. A figura conceitual de três áreas do slide 2 deve ser removida, não apenas acompanhada por uma ressalva oral.

> **Precisão sobre o fluxo da enfermaria:** no cenário operacional pretendido, o dashboard pode ficar disponível para a equipe do centro de enfermagem, que poderá visualizar os alertas enquanto acompanha o painel. Na implementação atual, o sistema exibe e registra alertas, mas não envia por conta própria notificações push, mensagens ou chamadas a profissionais identificados. A ação “Ir ao atendimento” registra uma intenção no sistema; não comprova atendimento presencial.

## Sequência recomendada e cronograma

| Tempo | Slide / trecho | Ação |
|---|---|---|
| 0:00–0:25 | 1 — Abertura | Apresentar nome e objetivo, sem prolongar a capa |
| 0:25–1:30 | 2 — Problema e escopo (revisar) | Explicar o problema e dizer o que o protótipo realmente faz |
| 1:30–2:20 | 3 — Fluxo de uso (revisar) | Apresentar entradas, análise, correlação e revisão humana |
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

Use uma capa revisada: **“Vigia Saúde — Monitoramento multimodal para revisão humana”**. Evite “inteligência multimodal clínica” se isso sugerir diagnóstico ou fusão clínica validada.

### 0:25–1:30 — Slide 2: problema e escopo

Substitua as três áreas atuais por um problema objetivo e pelas capacidades efetivamente implementadas. Sugestão de conteúdo visual:

- Entradas: vídeo gravado ou câmera; áudio associado à sessão.
- Imagem: pose e regras geométricas/cerca virtual.
- Fala: transcrição em português e regras locais de menções.
- Resultado: alerta e evidências para revisão humana.

**Fala:**

> “O desafio é reunir sinais de modalidades diferentes sem tratar um evento isolado como diagnóstico. Neste protótipo, a imagem é analisada por pose e regras de movimento; a fala é transcrita pelo Azure Speech e examinada por regras locais. Por exemplo, uma menção textual a ‘cansaço’ ou ‘fadiga’ pode gerar um aviso. Isso não significa que o sistema detecte fadiga pela voz. Também não há classificador de disartria, confusão, interação medicamentosa ou deterioração clínica; tampouco há monitoramento real de sinais vitais.”

### 1:30–2:20 — Slide 3: fluxo do sistema

Mantenha o esquema de coleta, processamento, correlação e revisão, mas substitua o subtítulo por **“Fluxo demonstrativo para revisão humana”**. Prefira “processamento local + serviços Azure” a “IA híbrida” sem explicação.

**Fala:**

> “O fluxo começa com vídeo e áudio de uma sessão. As duas modalidades são processadas separadamente; as evidências recebem referências temporais e podem ser correlacionadas. O dashboard permite que a equipe da enfermaria visualize os alertas se estiver implantado e sendo acompanhado. A aplicação não envia uma notificação direcionada fora do painel. O profissional continua responsável pela interpretação e pela decisão.”

### 2:20–3:20 — Slide 4: arquitetura

O diagrama atual é a parte mais informativa do deck. Ao apresentá-lo, aponte na ordem: entrada → vídeo local → fala/Azure → correlação → histórico → painel. Confirme se a imagem se mantém legível no modo de apresentação.

**Fala:**

> “No caminho da imagem, o backend local executa YOLOv8 Pose e aplica regras geométricas, incluindo a cerca virtual. No caminho de fala, o Azure Speech faz reconhecimento em português e regras locais identificam menções relevantes. Azure AI Language é uma integração opcional para texto, sentimento e termos-chave; ela não é necessária para o alerta demonstrado. A correlação de incidentes ocorre na aplicação, com janela de até dez segundos na mesma sessão, e o histórico fica em SQLite local.
>
> O diagrama separa a telemetria demonstrativa, que contém dados fictícios e não alimenta a análise multimodal.”

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
| 8:00–8:40 | Mostrar o dashboard disponível para a enfermaria e acionar “Ir ao atendimento” | “Em uma implantação no centro de enfermagem, a equipe que acompanha este dashboard pode visualizar o alerta. Vou registrar a intenção de atendimento no sistema; essa ação não dispara uma mensagem ou chamada para profissionais identificados nem confirma atendimento presencial.” |
| 8:40–9:20 | Abrir o histórico unificado | “O histórico permite consultar os incidentes e suas alterações após a sessão. Não é um prontuário e não inclui a telemetria fictícia.” |

**Demonstração de Azure:** para cumprir o requisito de integração, mostre Azure Speech realmente configurado e funcionando, se possível. Antes da gravação, confirme conectividade e credenciais no ambiente e faça um teste. Não exiba chaves, endpoints privados ou dados de configuração. Se usar uma execução simulada, não a apresente como chamada Azure real. Azure AI Language é opcional; não gaste tempo tentando demonstrá-lo caso não esteja ativo.

**Se usar a câmera ao vivo:** mostre que a prévia é local, configure e salve a cerca, então inicie explicitamente câmera e microfone. Não chame o fluxo de vídeo gravado de câmera ao vivo. A captura pode ter latência e perder movimentos entre amostras.

### 9:20–10:30 — Slide 4: interpretação técnica

> “A detecção visual combina keypoints do YOLOv8 Pose com regras geométricas; não é um classificador clínico de quedas. O Azure Speech transforma a fala em texto. Regras locais identificam menções como ‘cansaço’ ou ‘fadiga’ e podem gerar avisos; isso identifica as palavras reconhecidas, não sinais acústicos de fadiga. A disartria também não é classificada pela implementação: seria necessário um modelo específico, avaliado e validado para esse objetivo. O incidente multimodal usa timestamps e uma janela de até dez segundos na mesma sessão. Isso organiza evidências, mas não demonstra identidade, causalidade ou diagnóstico.”

### 10:30–11:30 — Slide 5: resultados e limites atuais

Use o slide para resumir testes de software e limites atuais. Deixe as melhorias futuras para o slide 6. Não use métricas de acurácia clínica: os testes E2E usam reconhecimento e inferência simulados.

**Fala:**

> “Os testes E2E documentados percorrem os principais fluxos da aplicação, incluindo alertas, correlação e histórico. A validação registrada teve quatro de quatro testes E2E aprovados, mas usa inferência YOLO e reconhecimento Speech simulados. Isso demonstra o funcionamento integrado do software, não a precisão dos modelos nem a eficácia clínica.
>
> Os resultados também dependem do enquadramento, iluminação, oclusão, qualidade do áudio e contexto da fala. A telemetria é fictícia e não há conexão com sensores ou prontuário. O dashboard pode ser disponibilizado à enfermaria para visualização, mas a versão atual não envia notificações direcionadas nem garante que alguém esteja acompanhando a tela.”

**Transição para o roadmap:**

> “Com esses limites claros, o próximo slide mostra o que precisaria ser desenvolvido e validado antes de considerar uma implantação hospitalar.”

### 11:30–14:00 — Slide 6: melhorias futuras

Adicione um slide após resultados/limitações. Use uma imagem conceitual gerada pelo Gemini com quatro figuras independentes, acrescente os títulos no PowerPoint (não peça ao gerador para renderizar texto) e apresente-as como etapas futuras. Título sugerido: **“Próximos passos para uma implantação responsável”**. Subtítulo opcional: **“Roadmap — não implementado nesta versão”**.

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
> As quatro cenas devem parecer uma proposta de roadmap, não uma arquitetura operacional presente. Use separadores visuais leves ou setas pontilhadas discretas, sem mostrar fluxo de dados atual. Evite imagens de pacientes identificáveis, cenas alarmistas, diagnósticos, promessas de prevenção de quedas, classificações automáticas de fadiga/disartria ou resultados numéricos. Não mostre o dashboard atual como se já enviasse notificações externas. Preserve áreas limpas para sobrepor os títulos: “Validar”, “Integrar”, “Operacionalizar” e “Governar”.

#### Títulos para inserir no PowerPoint

1. **Validar com evidências**
2. **Integrar dados clínicos**
3. **Operacionalizar alertas**
4. **Proteger e governar dados**

Em fonte menor, use uma faixa superior ou rodapé: **“Roadmap futuro — não implementado nesta versão”**. Essa indicação é importante para que a imagem não pareça documentar funcionalidades atuais.

#### Falas para acompanhar cada figura

**Introdução do slide — 10 a 15 segundos**

> “Estas quatro figuras representam melhorias futuras, não capacidades já entregues. A ideia é mostrar o caminho necessário para sair de um protótipo funcional e chegar a uma solução avaliável e integrada com segurança.”

**1. Validar com evidências — cerca de 25 segundos**

> “Primeiro, precisamos avaliar os componentes com dados autorizados e desidentificados, rótulos independentes e métricas claras de acerto, falso positivo, falso negativo e latência. Só depois de uma avaliação reproduzível e validação clínica faria sentido discutir o uso de novos classificadores. Azure Speech transcrever a fala, por si só, não identifica disartria nem fadiga vocal.”

**2. Integrar dados clínicos — cerca de 25 segundos**

> “A segunda frente seria integrar fontes reais, como sinais de equipamentos e sistemas hospitalares, usando padrões e autorização institucional. Hoje, a telemetria do painel é fictícia e não vem de sensores nem do prontuário; essa integração exigiria desenho técnico, governança e validação próprios.”

**3. Operacionalizar alertas — cerca de 25 segundos**

> “A terceira frente é transformar o painel em um fluxo operacional acordado com a enfermagem: definir quem acompanha, como um alerta é atribuído, confirmado e escalonado, e como registrar a resposta. Na versão atual, o dashboard exibe os alertas para quem o acompanha, mas não envia notificações direcionadas a profissionais.”

**4. Proteger e governar dados — cerca de 25 segundos**

> “Por fim, uma implantação exigiria políticas institucionais de consentimento, acesso por função, proteção dos dados, retenção, auditoria e resposta a incidentes. Segurança e privacidade precisam ser requisitos do desenho e verificados antes de qualquer piloto, não apenas uma característica visual do sistema.”

**Fecho do roadmap — cerca de 10 segundos**

> “Essas frentes dependem umas das outras: primeiro evidência e validação, depois integração e operação controlada, sempre com governança e supervisão humana.”

### 14:00–15:00 — Encerramento

> “Em síntese, o Vigia Saúde demonstra como evidências de imagem e fala podem ser processadas por componentes distintos, relacionadas no tempo e apresentadas em um histórico para revisão humana. O roadmap deixa claro que validação, integração hospitalar, operação de alertas e governança são etapas futuras. O valor desta entrega é tornar o fluxo técnico concreto e auditável, sem confundir uma demonstração de software com um dispositivo clínico validado. Obrigado.”

## Checklist antes de gravar

- [ ] Remover do slide 2 as alegações de cirurgia, detecção vocal de fadiga/disartria, confusão, sinais vitais reais, interação medicamentosa e deterioração clínica. Se mencionar fadiga, descrevê-la como detecção da palavra na transcrição, não como classificação acústica.
- [ ] Corrigir “decisão clínica proativa”, “em tempo real” e afirmações de segurança que não estejam comprovadas.
- [ ] Inserir a gravação da aplicação após a arquitetura e incluir o novo slide de roadmap com quatro melhorias futuras.
- [ ] Marcar visualmente o roadmap como futuro/não implementado; adicionar títulos no PowerPoint, não dentro da imagem gerada.
- [ ] Padronizar o deck em 16:9 ou validar o enquadramento atual em 4:3.
- [ ] Confirmar se Azure Speech e, se mostrado, Azure AI Language estão realmente ativos; distinguir isso de mocks.
- [ ] Garantir que o exemplo mostre áudio, vídeo, timestamps, alerta, correlação e histórico.
- [ ] Explicar que o dashboard pode exibir os alertas à equipe que o acompanha, enquanto “Ir ao atendimento” registra uma intenção e não envia notificação direcionada nem confirma atendimento.
- [ ] Usar mídia autorizada e desidentificada; ocultar credenciais, dados pessoais e informações sensíveis.
- [ ] Ensaiar a apresentação completa com cronômetro e manter a duração total em até 15 minutos.
- [ ] Publicar no YouTube ou Vimeo como público ou não listado e testar o link antes da entrega.

## Referências do projeto

- [Relatório técnico multimodal](./relatorio-tecnico-multimodal.md)
- [README do projeto](../README.md)
