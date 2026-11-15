# Roteiro de apresentação — Vigia Saúde

## Objetivo

Apresentar o projeto à banca de pós-graduação em tecnologia em até 15 minutos, demonstrando o processamento multimodal, a detecção e correlação de anomalias, o uso dos serviços Azure e o fluxo de revisão do alerta.

> **Precisão sobre o escopo:** a aplicação demonstra alertas na interface, registro da ação **“Ir ao atendimento”** e histórico auditável. Ela **não envia uma notificação real para a equipe médica**. O registro representa uma intenção no sistema, não comprova atendimento presencial. Apresente a integração com a equipe como evolução futura.

## Distribuição do tempo

| Tempo | Etapa | Objetivo |
|---|---|---|
| 0:00–0:50 | Abertura | Apresentar o problema e a proposta em uma frase |
| 0:50–2:00 | Problema e objetivo | Explicar por que combinar vídeo e fala |
| 2:00–3:30 | Arquitetura | Mostrar processamento local, Azure e histórico |
| 3:30–9:30 | Demonstração gravada | Percorrer o fluxo funcional da aplicação |
| 9:30–11:00 | Decisões técnicas | Explicar modelos, regras e correlação |
| 11:00–12:30 | Testes e resultados | Distinguir validação de software de validação clínica |
| 12:30–14:00 | Limitações e próximos passos | Demonstrar rigor técnico e responsabilidade |
| 14:00–15:00 | Conclusão | Retomar a proposta e encerrar |

Reserve aproximadamente seis minutos para a gravação da aplicação. Ensaie com cronômetro para manter a apresentação abaixo do limite de 15 minutos.

## Roteiro e falas

### 0:00–0:50 — Abertura

> “Boa tarde. Vou apresentar o Vigia Saúde, um protótipo de monitoramento multimodal. A ideia central é combinar evidências de vídeo e fala, organizadas por tempo, para facilitar a revisão de um possível evento por um profissional. Vou mostrar a arquitetura, o funcionamento da aplicação e, ao final, delimitar com precisão o que o sistema demonstra — e o que ainda não está validado.”

### 0:50–2:00 — Problema e objetivo

> “Em um cenário de cuidado, um sinal isolado pode não contar toda a história. Um movimento próximo ao leito e um pedido de ajuda, por exemplo, são evidências de naturezas diferentes. O objetivo deste projeto foi construir um fluxo que processe vídeo e áudio, associe eventos próximos no tempo e apresente essas evidências de forma rastreável.
>
> O escopo não é diagnosticar nem substituir a decisão clínica. É demonstrar como diferentes fontes podem ser reunidas em uma interface para apoiar a revisão humana.”

### 2:00–3:30 — Arquitetura

> “O vídeo é processado no backend local com YOLOv8 Pose e regras geométricas, incluindo uma cerca virtual. O áudio segue outro caminho: o Azure Speech realiza o reconhecimento de fala em português; regras locais analisam menções relevantes no texto. O Azure AI Language pode ser usado para analisar sentimento textual e extrair termos-chave.
>
> Cada evidência recebe referência temporal. Quando eventos de imagem e fala ocorrem na mesma sessão dentro da janela configurada de até dez segundos, o sistema pode reuni-los em um incidente. Os registros ficam no histórico local em SQLite.
>
> A telemetria visualizada na interface é demonstrativa e fictícia. Ela não vem de sensores e não participa da análise multimodal.”

**Transição para a demonstração:**

> “Agora vou percorrer um exemplo prático, do vídeo reproduzido até o alerta e seu registro no histórico.”

### 3:30–9:30 — Demonstração gravada

Prepare uma captura curta e organizada, usando mídia autorizada e não identificável. O cenário ideal contém uma saída da cerca e uma fala crítica próximas no tempo. Se usar material sintético, identifique-o como tal.

| Tempo | O que mostrar | Narração sugerida |
|---|---|---|
| 3:30–4:00 | Entrada no módulo de leito e visão geral | “Este é o módulo de monitoramento de leito. O cenário desta demonstração usa mídia preparada para a apresentação.” |
| 4:00–4:40 | Selecionar ou carregar o vídeo e conferir a cerca | “Vou iniciar a reprodução com a cerca virtual já configurada. A cerca permite demonstrar uma regra de movimento; sua saída não comprova uma queda.” |
| 4:40–6:20 | Reproduzir o vídeo; mostrar análise visual e transcrição | “O vídeo é analisado localmente. Em paralelo, o áudio reproduzido é encaminhado ao Azure Speech para reconhecimento em português. A transcrição e os eventos podem surgir em momentos diferentes.” |
| 6:20–7:30 | Mostrar a saída da cerca e a fala crítica; destacar timestamps | “Aqui aparecem as evidências de imagem e de fala. Primeiro, cada alerta pode ser apresentado individualmente. Quando os eventos são próximos no tempo e pertencem à mesma sessão, o sistema pode correlacioná-los.” |
| 7:30–8:25 | Mostrar o incidente multimodal e a tela de atendimento | “O resultado é um incidente com as evidências identificadas e seus horários. O alerta solicita revisão; não é um diagnóstico.” |
| 8:25–9:00 | Registrar “Ir ao atendimento” | “Vou registrar a ação no sistema. Esse registro é auditável, mas não envia uma notificação externa nem confirma que alguém foi atendido.” |
| 9:00–9:30 | Consultar o histórico | “Por fim, o histórico preserva o incidente e suas alterações, permitindo consultar o que foi registrado.” |

Se o Azure AI Language estiver configurado e houver tempo, mostre a análise do texto:

> “Além do reconhecimento de fala, o Azure AI Language pode calcular indicadores sobre o texto e extrair termos-chave. Esse resultado é complementar; não é uma avaliação clínica e não é necessário para a regra de alerta demonstrada.”

Se a integração não estiver ativa no ambiente gravado, não simule uma resposta real. Mencione-a como integração opcional da solução.

### 9:30–11:00 — Decisões técnicas

> “A separação entre processamento local e serviços Azure deixa explícitos os papéis de cada componente. O YOLOv8 Pose fornece pontos corporais; são as regras geométricas que identificam condições como a saída da cerca. No áudio, o Speech fornece a transcrição, e regras locais procuram menções relevantes.
>
> A correlação de até dez segundos organiza evidências próximas, mas não prova que a fala veio da pessoa acompanhada, que houve causalidade ou que ocorreu uma emergência. Essa distinção é importante para interpretar corretamente o resultado.”

### 11:00–12:30 — Testes e resultados

> “A implementação tem testes automatizados para percorrer os principais fluxos, incluindo correlação, registro e consulta ao histórico. Os testes de integração documentados usam inferências e reconhecimento simulados para validar o comportamento do software.
>
> Isso comprova o fluxo funcional da aplicação, mas não mede a precisão do YOLO ou do Azure em pacientes reais. Também não é uma validação clínica. Portanto, apresento separadamente o que foi testado no software e o que ainda exigiria avaliação dos modelos com dados autorizados e rotulados.”

O relatório do projeto registra **4 de 4 testes E2E aprovados** para os fluxos descritos. Apresente esse dado sempre com a ressalva de que inferência e reconhecimento nesses testes foram simulados.

### 12:30–14:00 — Limitações e próximos passos

> “Há limitações importantes: enquadramento, oclusão, iluminação, qualidade do áudio e contexto da fala podem afetar os resultados. As regras e limiares são heurísticas, não critérios clínicos validados. A telemetria é fictícia; não há integração com sensores, prontuário ou notificação real da equipe.
>
> Como próximos passos, seriam necessários testes com dados autorizados e desidentificados, rótulos independentes, avaliação de desempenho e falsos positivos, validação clínica e uma integração segura com o fluxo de comunicação aprovado pelo hospital. A privacidade, o consentimento, o controle de acesso e a retenção dos dados também precisariam ser definidos para uma implantação real.”

### 14:00–15:00 — Conclusão

> “Em resumo, o Vigia Saúde demonstra um fluxo multimodal: vídeo e fala são processados por componentes distintos, suas evidências recebem referência temporal e podem ser reunidas em um histórico auditável para revisão humana. O protótipo ajuda a discutir como essa arquitetura poderia apoiar um fluxo hospitalar, mas não substitui avaliação clínica e ainda não notifica uma equipe real.
>
> O principal resultado do projeto é tornar esse fluxo concreto e verificável — incluindo suas fronteiras. Obrigado.”

## Recomendações para uma apresentação forte

- Comece pelo valor e pelo problema; apresente as tecnologias depois.
- Na demonstração, oriente o olhar da banca antes de cada ação: transcrição, horário, alerta, correlação e histórico.
- Mostre a integração Azure com evidência visual, se o ambiente estiver configurado para chamadas reais. Diferencie serviço real de teste simulado.
- Grave e revise a demonstração antes da apresentação. Confira a clareza do áudio, visibilidade do cursor, duração e ausência de notificações ou dados pessoais.
- Tenha uma gravação de contingência caso Azure ou a rede falhem ao vivo. Esclareça se a captura foi feita com serviços reais ou mocks.
- Não leia a interface em voz alta: use os slides para resumir e a gravação para mostrar o comportamento.
- Reconheça explicitamente que o alerta não chega a uma equipe real. Apresente essa integração como uma evolução futura.

## Checklist de entrega do vídeo

- [ ] Duração total de até 15 minutos, incluindo apresentação e demonstração.
- [ ] Demonstração prática de análise de áudio e vídeo.
- [ ] Exemplo visível de anomalia e da resposta apresentada pela aplicação.
- [ ] Integrações Azure identificadas e demonstradas quando estiverem realmente ativas.
- [ ] Fluxo do alerta até a revisão/registro no sistema explicado sem afirmar que há notificação real à equipe médica.
- [ ] Mídia autorizada, sem identificação desnecessária de pacientes.
- [ ] Vídeo enviado ao YouTube ou Vimeo, como público ou não listado.
- [ ] Link do vídeo verificado em janela privada ou sessão sem autenticação, conforme a configuração de privacidade escolhida.
- [ ] Ressalvas sobre telemetria fictícia, ausência de validação clínica e uso de testes simulados apresentadas.

## Referências do projeto

- [Relatório técnico multimodal](./relatorio-tecnico-multimodal.md)
- [README do projeto](../README.md)
