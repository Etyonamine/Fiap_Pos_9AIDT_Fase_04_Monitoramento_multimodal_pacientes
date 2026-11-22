<!-- pt-BR -->
# Entrega — Tech Challenge | Fase 4

**Tema:** IA integrada aos processos médicos da instituição<br>
**Projeto:** Monitoramento multimodal de pacientes<br>
**Instituição:** FIAP

## Materiais da entrega

| Material | Acesso |
|---|---|
| Repositório com o código-fonte | [Fiap_Pos_9AIDT_Fase_04_Monitoramento_multimodal_pacientes](https://github.com/Etyonamine/Fiap_Pos_9AIDT_Fase_04_Monitoramento_multimodal_pacientes) |
| Vídeo de apresentação | [Assistir no YouTube](https://youtu.be/H27aF9EXlQk) |
| Relatório técnico completo | [relatorio-tecnico-multimodal.md](./relatorio-tecnico-multimodal.md) |
| Apresentação revisada | [Vigia-Saude-apresentacao-revisada.pptx](./Vigia-Saude-apresentacao-revisada.pptx) |
| Enunciado oficial | [IADT - Fase 4 - Tech challenge.pdf](./IADT%20-%20Fase%204%20-%20Tech%20challenge.pdf) |

## Resumo executivo

O projeto implementa um protótipo multimodal para analisar vídeo e áudio e
reunir evidências de uma mesma sessão. O vídeo é processado localmente com
YOLOv8 Pose e regras geométricas; a fala é transcrita com Azure Speech e
examinada por regras locais. Azure AI Language pode analisar sentimento e
termos-chave do texto. Incidentes de imagem e fala podem ser correlacionados
por proximidade temporal e consultados em histórico auditável.

A solução é um **protótipo de apoio à revisão**, não um dispositivo clínico.
Os testes e as demonstrações descritos neste documento usam mídia, inferências
ou sensores simulados; não demonstram acurácia clínica nem atendimento de uma
equipe médica.
O endpoint de consulta da ingestão contínua também não implementa autenticação
de usuário; não exponha a aplicação em rede não confiável nem use dados reais
sem controles institucionais de acesso e transporte seguro.

Atualização do protótipo: além do simulador, há uma API autenticada para
ingestão contínua HTTP e recepção de Bundles FHIR R4 em uma sessão de mídia
ativa. As amostras podem ser correlacionadas temporalmente com evidências da
mesma sessão e gerar eventos genéricos para a fila de webhook. Há também uma
comparação acústica exploratória com gravação de referência. Essas capacidades
não equivalem a sensores ou prontuário institucional conectados, identidade
clínica, detecção vocal validada ou alertas recebidos por equipe real. O vídeo
publicado ainda precisa ser regravado para demonstrar esta versão. Os PDFs
incluídos no repositório foram regenerados a partir dos documentos atuais.

O painel também aceita importação manual de CSV/JSON com séries de sinais
vitais e histórico de prescrições, além de uma nota clínica JSON desidentificada
com autorização explícita para envio do texto ao Azure AI Language. A consulta
FHIR R4 manual e contínua e o webhook opcional foram exercitados localmente
com dados/serviços sintéticos. A aplicação não remove identificadores
automaticamente. Ainda não há sensores conectados, prontuário institucional ou
destinatário de equipe reais verificados, nem correlação de identidade entre
importações distintas. Os nomes dos arquivos importados e resultados derivados
ficam no SQLite local; use nomes sem identificadores pessoais.

## Fluxo e componentes

```mermaid
flowchart LR
    V["Vídeo gravado ou câmera"] --> F["FFmpeg e preparação local"]
    F --> Y["YOLOv8 Pose e regras geométricas"]
    A["Áudio de gravação ou microfone"] --> S["Azure Speech · pt-BR"]
    S --> R["Regras locais sobre o texto"]
    S --> L["Azure AI Language · opcional"]
    N["Nota clínica · autorização explícita"] --> L
    Y --> E["Evidências com timestamp"]
    R --> E
    E --> C["Correlação temporal de até 10 s"]
    C --> DB["SQLite · incidentes e auditoria"]
    DB --> UI["Painel, relatórios e histórico"]
    DB --> W["Webhook opcional para alertas confirmados"]
    L --> UI
    CSV["CSV/JSON clínico · importação manual"] --> UI
    FHIR["FHIR R4 opcional · consulta autorizada"] --> UI
    FEED["HTTP/FHIR · ingestão autenticada"] --> DB
    DB --> W
```

### Métodos por modalidade

| Dado | Método ou serviço | Uso e limites |
|---|---|---|
| Vídeo e imagem | YOLOv8 Pose com pesos locais | Estima keypoints corporais. As regras calculam ângulos e acompanham o sujeito; não classificam quedas ou condições clínicas. |
| Leito | Cerca virtual baseada no ponto médio dos quadris | Registra evento quando o sujeito acompanhado sai do retângulo configurado. Isso não comprova queda ou emergência. |
| Fisioterapia | Regras geométricas sobre keypoints | Exemplos de limites configuráveis: tronco acima de 35°, joelho abaixo de 60° e elevação do tronco acima de 15° em relação à referência deitada. São heurísticas 2D; a postura é informada pelo usuário. |
| Áudio e fala | Azure Speech SDK, reconhecimento contínuo em `pt-BR` | Produz transcrição e tempos dos trechos. A consulta apresenta estimativas de palavras por minuto e pausas com base na transcrição/segmentação, não em diagnóstico ou avaliação acústica de disartria/fadiga. |
| Texto reconhecido | Regras lexicais locais | Sinaliza menções como falta de ar, dor no peito, socorro, cansaço e fadiga, com tentativa heurística de reconhecer negação. Pode gerar falsos positivos e negativos. |
| Texto de consulta | Azure AI Language / Text Analytics v3.1 | Extrai sentimento do texto e termos-chave quando configurado. Sentimento textual não representa emoção vocal ou condição clínica. |
| Sinal acústico | Energia, pitch exploratório, cruzamentos por zero e comparação com gravação de referência | Descritores dependem de segmentos reconhecidos como fala e não são detectores validados de fadiga, disartria ou dificuldade respiratória. |
| Sinais vitais e prescrições | Importação manual, API HTTP autenticada e Bundles FHIR R4 | Há regras genéricas para revisão, associação temporal à sessão e persistência limitada. Não há sensores/prontuário institucional conectados nem validação de dose, indicação ou interação. |
| Nota clínica | JSON com texto enviado ao Azure AI Language após autorização | O original não é persistido localmente; sentimento e menções não são diagnóstico. |
| Notificação | Webhook opcional com fila e chave de idempotência | Recebe alertas de mídia confirmados e eventos clínicos genéricos da ingestão contínua. Testado com destinatário local sintético; resposta 2xx não comprova comunicação com uma equipe nem atendimento. |

## Resultados documentados

- **Testes E2E:** 6 de 6 passaram em Chromium, cobrindo gravação de leito com
  incidente imagem–fala e histórico, análise de fisioterapia e relatório,
  importação de consulta com consentimento, câmera/microfone simulados e
  importação dos exemplos clínicos sintéticos, além de FHIR e webhook locais.
  O cenário de câmera também verifica a ingestão autenticada do Bundle FHIR,
  o mapeamento para o tempo da sessão, a evidência de mídia correspondente e
  a entrega do evento genérico ao webhook sintético.
- **Validação local após as alterações atuais:** 382 testes backend, 119
  Angular, 4 AudioWorklet e os 6 cenários E2E passaram. A comparação acústica
  com referência tem testes focados; ela não foi incluída no E2E de navegador.
- **Correções posteriores revalidadas localmente:** a origem temporal da
  câmera agora é imutável, eventos antes da origem do vídeo são rejeitados
  mesmo em reprodução com deslocamento e cada Bundle FHIR é integralmente
  confirmado ou revertido numa transação. A suíte local completa após as
  correções passou; a CI precisa executar novamente neste commit de trabalho.
- **Build Angular:** concluído; permaneceram avisos de orçamento SCSS em
  `telemetry.scss` e `video-workspace.scss`.
- **Cobertura de código medida localmente após as correções:** backend da
  aplicação 93,88% de linhas e 88,10% de branches; Python (aplicação e
  avaliador), 94,03% e 88,13%;
  frontend Angular e templates, 91,15% e 82,02%, respectivamente.
  Cobertura mede execução de código, não qualidade preditiva dos modelos.
- **Azure real:** Speech e AI Language retornaram respostas a um WAV e texto
  sintéticos, respectivamente, em verificação pontual separada dos testes
  automatizados. Não demonstra desempenho clínico ou implantação em Azure.
- **Avaliador offline sintético:** com tolerância temporal de 0,5 s, o exemplo
  produziu TP=2, FP=1, FN=1, precisão=0,667, recall=0,667, F1=0,667,
  WER=0,4 e MAE angular=2,5°. Esses valores verificam o cálculo das métricas;
  não são resultados de YOLO ou dos serviços Azure em mídia real.
- **Exemplos funcionais:** saída da cerca, menção crítica de fala, correlação
  imagem–fala na mesma sessão em até 10 s, regras geométricas de fisioterapia
  e indicadores de qualidade de áudio.

## Conferência dos requisitos do Tech Challenge

Esta conferência compara o enunciado, o código e o relatório técnico
disponíveis no repositório. “Parcial” indica que há uma demonstração ou parte
da funcionalidade, mas não todo o requisito conforme descrito. A conferência
documental não substitui validação clínica, verificação de serviços hospitalares
ou revisão integral do vídeo de apresentação.

| Requisito do enunciado | Situação | Evidência e observação |
|---|---|---|
| Analisar vídeos clínicos e detectar movimentos ou eventos fora do padrão | **Parcial** | Há análise de fisioterapia por pose e evento de saída da cerca em leito. Não há classificação específica de cirurgia ou validação clínica das anomalias. |
| Gerar relatórios automáticos de desvios ou falhas | **Atendido parcialmente** | A fisioterapia permite baixar relatório JSON com eventos. Os desvios são heurísticos e não validam execução clínica. |
| Processar áudio de consultas médicas | **Implementado no código** | O fluxo importa áudio, exige consentimento e integra Speech; os testes E2E usam reconhecimento simulado. |
| Detectar alterações vocais, como fadiga ou disartria | **Parcial / não validado clinicamente** | Há comparação acústica exploratória com referência (pitch, energia e cruzamentos por zero) em segmentos reconhecidos como fala, além de regras sobre texto transcrito. Não existe conjunto autorizado/rotulado ou classificador avaliado para fadiga ou disartria; a comparação não diagnostica. |
| Usar Azure Speech e Azure Text Analytics/AI Language | **Implementado; conectividade real pontual verificada** | Speech e Language responderam a áudio e texto sintéticos; os testes automatizados usam simulações. A transcrição recebe regras locais de termos críticos; Language fornece sentimento e key phrases, não análise acústica ou diagnóstico. |
| Detectar anomalias em sinais vitais, prescrições e evolução clínica | **Parcial, regras demonstrativas** | Há importação manual e ingestão contínua HTTP/FHIR autenticada, com validação, comparação temporal e eventos genéricos. As regras não têm validação clínica; não há sensor ou prontuário institucional conectado nem avaliação de dose/indicação/interação. |
| Alertar a equipe médica em tempo real | **Parcial; integração institucional pendente** | Eventos da ingestão contínua e alertas de mídia confirmados podem entrar na fila de webhook. O envio é configurável, mas não há destinatário de equipe, SLA/latência, confirmação de leitura ou atendimento verificados. |
| Analisar e fundir dados médicos de texto, áudio e vídeo | **Parcial** | A aplicação correlaciona evidências visuais, fala e amostras clínicas por sessão e proximidade temporal. Não há fusão de laudos/documentos clínicos reais ou identidade segura entre sistemas. |
| Usar serviços em nuvem para ampliar processamento e inteligência | **Parcial** | Speech e Language são integrados como serviços Azure; a inferência YOLO é local. Não há evidência de implantação integral ou de processamento de vídeo na nuvem. |
| Aplicar detecção de anomalias em tempo real | **Parcial** | A sessão ativa aceita ingestão contínua HTTP/FHIR e executa regras demonstrativas; a interface pode acompanhar os dados. Não há sensor real conectado nem garantia de latência clínica. |
| Disponibilizar o código-fonte completo em repositório Git | **Atendido, conforme material disponível** | O repositório do projeto está indicado acima. |
| Entregar relatório técnico com fluxo multimodal, modelos, resultados e exemplos | **Atendido** | Esses tópicos constam no [relatório técnico](./relatorio-tecnico-multimodal.md). |
| Entregar vídeo público ou não listado, com até 15 minutos e demonstração dos fluxos solicitados | **Link presente; conteúdo não verificado integralmente** | A duração observada foi 12min57s, abaixo do limite. Ainda é necessário conferir visibilidade, conteúdo completo e demonstração das alterações posteriores. |

### Pendências prioritárias frente ao enunciado

1. Configurar e verificar, com autorização institucional, um destinatário real
   para o webhook, sua autenticação, deduplicação, fluxo de resposta e latência.
   O recebimento técnico isolado não comprova atendimento.
2. Conectar a API a fontes reais autorizadas de sinais/prontuário e validar
   compatibilidade do servidor FHIR, operação de assinatura, segurança de
   transporte e associação institucional de identidade. O receptor existe, mas
   não configura uma assinatura remota; regras e massa atuais permanecem
   demonstrativas.
3. Repetir e registrar a verificação de Azure Speech e Language no ambiente
   final sem expor chaves; a verificação pontual já realizada não garante
   disponibilidade contínua.
4. Regravar e conferir o vídeo após as mudanças: demonstrar o mapeamento
   temporal FHIR e a rejeição/rollback de Bundles inválidos, além de verificar
   visibilidade, limite de 15 minutos, análise de áudio/vídeo, Azure e fluxo de
   alerta. A gravação publicada não foi alterada nesta implementação.
5. Para alegações de desempenho clínico, realizar avaliação futura com mídia
   autorizada/desidentificada, rótulos independentes e predições reais. O
   avaliador já existente e seus exemplos sintéticos não substituem essa etapa.

## Configuração segura do Azure

Para a execução local, copie `backend/.env.example` para `backend/.env` e
configure as variáveis abaixo com credenciais dos recursos correspondentes:

| Variável | Finalidade |
|---|---|
| `AZURE_SPEECH_KEY` | Chave do recurso Azure Speech |
| `AZURE_SPEECH_REGION` | Região do recurso Azure Speech |
| `AZURE_LANGUAGE_KEY` | Chave do recurso Azure AI Language |
| `AZURE_LANGUAGE_ENDPOINT` | Endpoint HTTPS do recurso Azure AI Language |
| `FHIR_BASE_URL`, `FHIR_BEARER_TOKEN` | Consulta FHIR opcional, quando houver servidor autorizado |
| `CLINICAL_INGEST_BEARER_TOKEN` | Token independente, com ao menos 32 caracteres, para ingestão HTTP/FHIR |
| `ALERT_WEBHOOK_ENABLED`, `ALERT_WEBHOOK_URL`, `ALERT_WEBHOOK_BEARER_TOKEN` | Webhook opcional; desativado por padrão |

Não publique o arquivo `.env` nem inclua chaves neste documento, no repositório
ou no vídeo. Consulte o [README do projeto](../README.md) para detalhes de
configuração, execução e verificação. A configuração local não equivale a
provisionamento ou implantação da aplicação no Azure.

> **Atenção:** se credenciais reais foram compartilhadas anteriormente ou
> incluídas em arquivos versionados, revogue-as no Azure, gere novas e verifique
> também os PDFs de entrega antes de distribuí-los.

## Referências

- [Relatório técnico completo](./relatorio-tecnico-multimodal.md)
- [Enunciado do Tech Challenge](./IADT%20-%20Fase%204%20-%20Tech%20challenge.pdf)
- [README do repositório](../README.md)
