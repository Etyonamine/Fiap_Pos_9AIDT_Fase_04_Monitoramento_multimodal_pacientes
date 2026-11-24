# Plano de gravação final em 1 hora

## Objetivo

Produzir, em uma hora, uma apresentação final entre **11 e 13 minutos**,
abaixo do limite de 15 minutos, com potencial de:

- **70/90:** atendimento acadêmico seguro;
- **80/90:** apresentação técnica bem demonstrada;
- **85–90/90:** entrega clara, rastreável, sem exageros clínicos.

Esses valores são metas operacionais, não uma nota oficial garantida.

## Estratégia mais segura

Não faça uma demonstração ao vivo de todos os componentes. Use:

1. o PowerPoint corrigido para abertura, problema, escopo e arquitetura;
2. a V3 validada, reproduzida **sem áudio**, como demonstração gravada;
3. sua nova voz, ao vivo, explicando cada resultado;
4. o material de E2E somente como contingência.

Arquivos principais:

- apresentação:
  `docs/TechChallenge_Fase_4_Apresentacao_11_2026_v1 - Copiar.pptx`;
- vídeo B-roll validado:
  `data/video/FIAP-TC-FASE-4-video-v3.mp4`;
- projeto e documentação no repositório atual;
- exemplos sintéticos em `backend/evaluation/examples`;
- detalhes adicionais em `docs/plano-edicao-video-final.md`.

A V3 deve ficar **muted**. O áudio original dela não deve disputar com a nova
locução.

## Regras de postura de apresentação

- Fale olhando para a câmera na abertura e no encerramento.
- Na demonstração, esconda a webcam ou deixe-a pequena e fixa em um canto.
- Não use a palavra “detecção clínica”.
- Não diga que o sistema “identificou fadiga” ou “detectou disartria”.
- Não diga que o webhook notificou uma equipe real.
- Não diga que “Aceito pelo destino” significa atendimento.
- Use “protótipo acadêmico”, “dados sintéticos”, “revisão humana” e
  “perfil acústico artificial”.
- Não tente improvisar configurações ou credenciais na gravação.
- Nunca pause para diagnosticar erro. Use o roteiro de contingência.

## Cronograma de uma hora

| Tempo | Ação | Entregável |
|---:|---|---|
| 0–10 min | Abrir PowerPoint, V3 e gravador; silenciar V3; ensaiar a abertura uma vez | Ambiente pronto |
| 10–18 min | Gravar bloco 1: abertura, problema, escopo e arquitetura | 2–3 min |
| 18–38 min | Gravar bloco 2: demonstrar fisioterapia, voz, leito e complementos usando V3 | 7–9 min |
| 38–48 min | Gravar bloco 3: testes, limites, contribuição e fechamento | 2 min |
| 48–55 min | Revisar rapidamente e refazer somente um trecho crítico, se necessário | Correção pontual |
| 55–59 min | Exportar em 1080p e conferir início, meio e fim | MP4 final |
| 59–60 min | Salvar cópia com nome final e anotar local/link | Entrega pronta |

Não faça uma edição complexa. Recorte apenas:

- falas incompletas;
- silêncios;
- erros factuais;
- tela branca.

## Estrutura exata do vídeo

| Tempo final | Bloco | Forma | Conteúdo obrigatório |
|---|---|---|---|
| 00:00–00:30 | Abertura | Câmera | Nome, FIAP, objetivo, aviso de protótipo |
| 00:30–02:00 | Problema e escopo | PowerPoint | Quatro capacidades e limites |
| 02:00–02:40 | Arquitetura | PowerPoint | YOLO, Speech, Language opcional, SQLite, HTTP/FHIR |
| 02:40–04:10 | Fisioterapia | V3 mudada, sem áudio | 150°, recálculo, relatório e evento |
| 04:10–05:30 | Voz | V3 mudada, sem áudio | Transcrição, termos, perfil acústico artificial |
| 05:30–07:30 | Leito e fusão | V3 mudada, sem áudio | Cerca, fala, correlação, alerta e histórico |
| 07:30–08:45 | Evolução sintética | V3 mudada, sem áudio | Introdução, persistência e resolução |
| 08:45–09:35 | FHIR | V3 mudada, sem áudio | `synthetic-patient`, dado local e limite do receptor |
| 09:35–11:10 | Testes e limites | Slide | 415, 131, 4, 6/6, cobertura, ausências |
| 11:10–12:20 | Contribuição acadêmica | Câmera/slide | O que foi integrado e por que importa |
| 12:20–13:00 | Fechamento | Câmera | Próximos passos e agradecimento |
| 13:00 | Fim |  | Margem de 2 minutos antes do limite |

## Roteiro de fala

### 00:00–00:30 — Abertura

> “Boa noite. Meu nome é Eduardo Toshio Yonamine e este é o Vigia Saúde, meu
> protótipo para o Tech Challenge da fase quatro. A proposta é reunir evidências
> de vídeo, fala e dados sintéticos em uma mesma linha temporal para revisão
> humana. Esta é uma demonstração acadêmica: ela não é um dispositivo clínico,
> não produz diagnóstico e não comprova atendimento de equipe médica.”

Texto em tela:

> **Vigia Saúde — Monitoramento multimodal para revisão humana**

### 00:30–02:00 — Problema, escopo e importância

> “O problema central é integrar sinais diferentes sem transformar uma
> coincidência em diagnóstico. O módulo de vídeo usa pose e regras geométricas.
> O módulo de voz usa Speech, menções na transcrição e comparação acústica
> exploratória. Sinais vitais e prescrições entram por importação, HTTP ou FHIR.
> O resultado é um conjunto de evidências, com timestamp, histórico e evento de
> revisão.
>
> Para esta demonstração, vídeo, áudio, inferências e integrações são sintéticos
> ou simulados. O valor acadêmico está na implementação ponta a ponta, na
> rastreabilidade e na forma honesta de separar resultado técnico, hipótese e
> validação clínica ainda ausente.”

Mostre quatro cartões:

1. imagem;
2. voz;
3. sinais/prescrições;
4. revisão humana.

### 02:00–02:40 — Arquitetura

> “No caminho de imagem, o backend usa FFmpeg e YOLOv8 Pose. No caminho de fala,
> Azure Speech produz a transcrição e regras locais procuram menções relevantes.
> Azure AI Language é opcional para o texto. A aplicação correlaciona evidências
> na mesma sessão e guarda incidentes e auditoria em SQLite. HTTP e FHIR são
> recebidos em endpoints autenticados. Um webhook de teste pode receber o evento,
> mas isso confirma somente a entrega técnica.”

Mostre a linha:

> **Entrada → Processamento → Correlação temporal → Revisão humana**

Adicione por voz:

> “Correlação temporal não significa identidade do paciente nem causalidade.”

### 02:40–04:10 — Fisioterapia

Abra a V3 em **01:40** e deixe a aplicação aparecer.

Ao iniciar:

> “Neste caso sintético, selecionei postura em pé e alterei o limite interno do
> joelho para 150 graus. Esse número existe apenas para tornar o desvio
> mensurável; ele não é uma recomendação clínica.”

Ao aparecer o cálculo:

> “O sistema recalcula os eventos e o relatório mantém o mesmo limite de 150
> graus. A saída contém o evento geométrico, o tipo de postura e o aviso de não
> diagnóstico.”

Mostre por alguns segundos:

- `150°`;
- evento `Ângulo interno do joelho < 150°`;
- relatório.

Frase final obrigatória:

> “O protótipo sinaliza um desvio geométrico para revisão; ele não avalia a
> execução fisioterapêutica.”

### 04:10–05:30 — Voz

Continue na V3 até o complemento de voz.

> “Na voz, separo duas evidências. A transcrição pode produzir uma menção como
> ‘falta de ar’; essa evidência vem do texto reconhecido. Separadamente, a
> aplicação compara pitch, variação do pitch, energia e cruzamentos por zero
> entre duas gravações.”

Ao aparecer o complemento:

> “A versão atual também possui um detector demonstrativo de perfil acústico
> artificial, incluindo controle semelhante e abstenção para entrada insuficiente.
> Ele não detecta fadiga, disartria, dificuldade respiratória ou diagnóstico.”

Frase obrigatória:

> “A coexistência entre uma diferença acústica e uma menção textual não demonstra
> causalidade.”

### 05:30–07:30 — Leito, cerca, fala e histórico

> “No módulo de leito, a cerca virtual gera uma evidência quando o sujeito
> acompanhado ultrapassa o limite configurado. A fala reconhecida gera uma
> segunda evidência. Como as duas pertencem à mesma sessão e ficam próximas no
> tempo, a aplicação mostra um incidente multimodal.”

Enquanto a tela aparece:

> “O vídeo permanece visível, o alerta aparece com o timestamp e a transcrição.
> Essa correlação organiza evidências; não identifica a pessoa e não prova queda
> ou emergência.”

Ao mostrar histórico:

> “O incidente pode ser consultado posteriormente, e a aplicação registra
> alterações e ações do usuário. O botão ‘Ir ao atendimento’ registra uma
> intenção; não confirma que alguém se deslocou ou realizou atendimento.”

Frase para webhook:

> “Aceito pelo destino significa somente que o receptor técnico respondeu; não
> significa que uma equipe recebeu, leu ou atendeu.”

### 07:30–08:45 — Evolução sintética

> “A evolução textual da versão atual não persiste o texto da nota. Ela armazena
> somente menções derivadas para uma sessão sintética. No exemplo, ‘cansaço’ é
> introduzido, permanece na segunda amostra e deixa de aparecer na terceira.”

Mostre os três cartões:

- introdução: cansaço;
- persistência: cansaço mantido;
- resolução: cansaço não observado.

Feche:

> “Isso demonstra uma transição no conjunto de menções. Não significa melhora,
> agravamento, diagnóstico ou identidade clínica.”

### 08:45–09:35 — FHIR sintético

> “Também demonstro a consulta FHIR local. O identificador
> `synthetic-patient` consulta um servidor sintético isolado. O retorno contém
> frequência cardíaca de 132 batimentos por minuto e uma prescrição sintética.
> Nenhum servidor hospitalar ou paciente real é acessado.”

Frase final:

> “HTTP/FHIR usa autenticação; nesta gravação, tanto a fonte quanto o receptor
> são locais, temporários e sintéticos.”

### 09:35–11:10 — Testes, cobertura e limites

Troque para o slide de resultados.

> “A versão validada passou por 415 testes backend, 131 testes Angular, quatro
> testes do AudioWorklet e seis de seis cenários E2E. O gate verificou cobertura
> aproximada de 94 por cento no backend e 93 por cento no frontend. Esses
> resultados demonstram contratos, integração, regressões e qualidade de
> software.”

Depois diga com clareza:

> “Eles não demonstram acurácia clínica. Ainda estão ausentes detecção vocal
> clínica validada, sensores reais, prontuário institucional, vínculo geral de
> identidade e destinatário de equipe verificado.”

Mostre a lista:

- validação clínica;
- integração institucional;
- segurança;
- governança.

### 11:10–12:20 — Contribuição

> “A contribuição principal é mostrar como diferentes evidências podem ser
> processadas de forma separada, correlacionadas por sessão e apresentadas com
> rastreabilidade. O projeto cobre movimento, fala, sinais, prescrições,
> evolução sintética, histórico e alertas sem esconder suas limitações. Em vez
> de substituir o julgamento humano, o protótipo organiza contexto para revisão.”

### 12:20–13:00 — Fechamento

> “Para evolução futura, o próximo passo é validar os modelos com dados
> autorizados e rotulados, integrar fontes e destinos institucionais, e implementar
> segurança, governança e avaliação operacional. O protótipo está implementado
> e demonstrado no escopo acadêmico. Obrigado.”

## Como usar a V3 com sua voz

1. Abra o arquivo V3 no player.
2. Deixe o áudio da V3 em **mudo**.
3. Posicione em **01:40**.
4. Inicie a gravação de tela com microfone.
5. Explique enquanto o vídeo toca.
6. Pause a V3 por 2–4 segundos:
   - no relatório de 150°;
   - no perfil acústico;
   - no incidente imagem–fala;
   - nos três estados de evolução;
   - no retorno FHIR.
7. Continue a narração.

Não use o trecho de áudio existente como se fosse uma nova gravação. Se a fala
original for mantida, trate-a como material já produzido e não a regravar
mentalmente.

## Plano de pontuação

### Para alcançar pelo menos 70/90

Obrigatório:

- apresentação até 15 minutos;
- objetivo e problema claros;
- demonstração das quatro modalidades;
- pelo menos um fluxo integrado;
- ao menos uma saída verificável, como relatório ou histórico;
- testes mencionados;
- limites clínicos explícitos;
- vídeo e repositório acessíveis.

### Para buscar 80–85/90

Acrescente:

- narrativa de arquitetura coerente;
- relação exata entre entrada, processamento e saída;
- FHIR e evolução atual;
- números atuais de testes;
- distinção entre demonstração técnica e validação;
- boa legibilidade e sem terminal.

### Para buscar 85–90/90

Acrescente:

- transições objetivas;
- uma única mensagem por cena;
- pausas reais nos resultados;
- cuidado de linguagem clínica;
- rastreabilidade dos testes até o fluxo demonstrado;
- encerramento com contribuição e próximos passos;
- nenhuma alegação maior que a evidência.

## Critérios de parada

Pare de refazer após:

- três blocos gravados;
- um MP4 exportado;
- voz inteligível;
- tela legível;
- nenhum segredo visível;
- abertura, testes e encerramento presentes.

Não gaste o tempo restante tentando melhorar animações, webcam ou trilha sonora.

## Contingência por tipo de falha

| Falha | Ação |
|---|---|
| Backend não inicia | Use a V3 muda e narre os trechos gravados |
| FHIR não responde | Mostre o clipe FHIR da V3 |
| Perfil acústico não aparece | Mostre o quadro-resumo da V3 |
| Evolução demora | Mostre os três estados já gravados |
| Voz trava | Regrave somente o bloco e continue pelos demais |
| Edição fica lenta | Concatene três blocos sem animações |
| Upload fica lento | Reserve a cópia local e use o link mais leve possível |

## Checklist final em 90 segundos

- [ ] Entre 11 e 13 minutos.
- [ ] Arquivo abre do início ao fim.
- [ ] Nenhum terminal ou explorador no quadro.
- [ ] Minha voz está inteligível.
- [ ] V3 está mutada quando usada como B-roll.
- [ ] Fisioterapia mostra 150° e relatório.
- [ ] Voz usa “perfil artificial”, não condição clínica.
- [ ] Leito mostra cerca, movimento, fala, alerta e histórico.
- [ ] Evolução mostra os três estados.
- [ ] FHIR está identificado como sintético/local.
- [ ] “Aceito pelo destino” é explicado corretamente.
- [ ] Contagens de testes estão atualizadas.
- [ ] Limites e próximos passos aparecem.
- [ ] Nenhum token, endpoint privado ou dado real aparece.
