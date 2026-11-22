# Backend de monitoramento

## Testes

O ambiente Windows de CI usa `requirements-test.lock.txt` (Python 3.14);
`requirements-test.txt` declara as dependências de testes, incluindo pytest-cov.
Execute a partir de `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests --cov=app --cov=evaluation --cov-branch --cov-report=json:coverage.json --cov-report=xml:coverage.xml -q
.\.venv\Scripts\python.exe -m evaluation demo --output evaluation-report.json
```

Os testes bloqueiam rede externa em sockets Python e removem configurações Azure,
FHIR e webhook herdadas; somente integrações simuladas são usadas. FFmpeg e SQLite são reais.
Além das regras de vídeo/voz/incidentes, há casos adversos de câmera e testes de
concorrência, orçamento de latência local e memória de polling. O helper SQLite
fecha conexões ao sair de `with`, preservando commit/rollback e liberando arquivos.
O servidor E2E isolado também remove configurações externas, bloqueia sockets
externos e substitui YOLO e Speech; FHIR e webhook são serviços sintéticos
locais. As rotas HTTP, FFmpeg e SQLite continuam reais.
Consulte o README da raiz para os pisos por módulo, comandos E2E e formato de
anotações do avaliador. Os exemplos do avaliador são sintéticos, não validação
do YOLO, Speech ou diagnóstico clínico.

Execute o backend a partir de `backend` com o ambiente virtual do projeto:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

O monitoramento de câmera usa a API em `/api/camera`. Antes de iniciar, salve uma
cerca ativada com `PUT /api/camera/fence`; não há cerca padrão para sessões
novas. `POST /api/camera/monitor` recebe `{ "fence": ..., "record": true|false }`.
Frames são enviados como JPEG com timestamp em segundos; áudio como WAV PCM16,
mono, 16 kHz, também com timestamp em segundos. `GET /api/camera/monitor/{id}`
retorna o snapshot atualizado. Alertas podem ser confirmados em
`POST /api/camera/monitor/{id}/acknowledge` e consultados em
`GET /api/camera/alert-log`.

Replay e câmera incluem `incidents` nos snapshots e no relatório de replay.
O serviço compartilhado correlaciona saída da cerca e falas críticas na mesma
sessão em até 10 s, pelo tempo da mídia, com a saída mais próxima como âncora.
Os alertas individuais não são atrasados, apagados nem substituídos.
Evidências incluem regra, origem, timestamp, estado, registro de ida e
transcrição final disponível (não retém uma fotografia do frame).
Correções provisórias, novas evidências e confirmações atualizam versões
auditáveis, na mesma transação dos alertas. Novas evidências não herdam o
registro de ida anterior. Correlação temporal não comprova identidade do
falante, causalidade, diagnóstico ou presença de uma equipe.

- `GET /api/incidents?limit=50&before=...`: histórico unificado paginado
  (câmera e gravações, inclusive sessões encerradas). Retorna `items` e
  `next_cursor`; sem cursor, começa pelos incidentes criados mais recentemente.
  `limit` aceita 1 a 100. Não inclui sinais/prescrições fictícias ou consultas.
- `GET /api/incidents/{id}/history?limit=50&before=...`: versões imutáveis
  em ordem decrescente de alteração, no mesmo formato de paginação.
- SQLite: `monitor_incidents` e `monitor_incident_log`. Inicialização incorpora
  sessões antigas com alertas, sem reexecutar YOLO ou Azure. Um incidente
  incorporado a outro mantém `merged_into` para auditoria e respostas
  assíncronas; não deve ser contado como incidente ativo. O histórico
  unificado já exclui essas incorporações.

Não há chamada adicional à nuvem para correlacionar ou consultar incidentes.
As transcrições associadas ficam no SQLite local junto dos registros existentes.

O início valida o modelo YOLO Pose e as variáveis `AZURE_SPEECH_KEY` e
`AZURE_SPEECH_REGION` sem fazer uma chamada de Language. Azure Speech é usado
para reconhecimento em fluxo; análise opcional de frases/sentimento usa
`AZURE_LANGUAGE_KEY` e `AZURE_LANGUAGE_ENDPOINT`. Não há chamadas a serviços
Azure nos testes automatizados.

Uma verificação pontual separada dos testes automatizados usou frase e áudio
sintéticos e recebeu respostas reais de Azure Speech e AI Language. Isso não
representa validação clínica ou implantação do backend na nuvem.

## Importação clínica manual

O router `/api/clinical-data` disponibiliza:

- `POST /vitals` e `POST /prescriptions`: CSV/JSON UTF-8, no máximo 5 MB e
  10.000 registros por arquivo. Sinais vitais exigem ISO 8601 com fuso,
  pseudônimo e FC/pressão/SpO₂. Regras fixas de limites e variações geram apenas
  eventos `review`. Prescrições são comparadas por medicamento e pseudônimo
  dentro do arquivo; não são verificadas contra uma ordem autorizada.
- `POST /notes`: JSON até 1 MB e texto até 12.000 caracteres. Requer
  `consent_to_cloud=true` e Azure AI Language configurado; envia o texto ao
  Language e não persiste o original. Desidentifique o texto antes do envio;
  não há remoção automática de nomes ou identificadores. Em falha Azure, nenhum
  resultado é salvo.
- `GET /imports`: lista as 200 importações mais recentes.
- `GET /examples/{vitals|prescriptions|note}`: baixa os arquivos sintéticos em
  `evaluation/examples`.
- `POST /fhir`: consulta manual e autorizada a FHIR R4 em modo somente leitura;
  exige `FHIR_BASE_URL` e `FHIR_BEARER_TOKEN`. Aceita `vitals` ou
  `prescriptions`, valida sujeito/código/unidade e apresenta avisos explícitos
  para dados ignorados. Não envia dados a Azure nessa operação.
- `POST /api/clinical-stream/{session_id}/samples`: recebe amostras contínuas
  com bearer token `CLINICAL_INGEST_BEARER_TOKEN` (mínimo 32 caracteres),
  UUID idempotente, pseudônimo estável da fonte, horário ISO 8601 e tempo da
  sessão. Rejeita amostras inválidas, fora de ordem ou de sessões encerradas.
- `POST /api/clinical-stream/{session_id}/fhir-subscription`: recebe Bundles
  FHIR R4 `collection`/`history` autenticados, com `source_id` pseudônimo e
  Observations/MedicationRequests compatíveis. Não cria a assinatura no
  servidor FHIR remoto.
- `GET /api/clinical-stream/{session_id}`: retorna as 100 amostras recentes,
  eventos e correlações de mídia até 10 s; a persistência é limitada a 1.000
  amostras por fonte/sessão. Este GET não exige o token de ingestão; mantenha a
  aplicação em rede confiável e não use dados reais sem autenticação/autorização
  institucional e HTTPS.

Resultados derivados são guardados na tabela SQLite `clinical_imports`, em
`VIDEO_DATA_DIR`. Identificadores de paciente são transformados em pseudônimos
escopados à importação, sem vínculo automático entre arquivos. Valores de sinais
vitais, campos de prescrição e nomes dos arquivos permanecem no banco local; use
nomes sem identificadores e não envie dados pessoais sem autorização e política
de retenção. O painel da telemetria reúne os eventos para revisão, mas as
importações manuais não são correlacionadas aos incidentes de mídia nem acionam
o webhook. A ingestão contínua HTTP/FHIR exige fonte autorizada, token no
backend e sessão de mídia ativa; não há sensor conectado por padrão. A consulta
FHIR manual foi testada somente com servidor sintético local; ordens não
equivalem a histórico de versões ou administração. Limites e comparações são
demonstrativos, sem validação clínica.

Na ingestão contínua, horários FHIR são convertidos em tempo da sessão. Para
câmera, o backend usa o `started_at` registrado ao criar a sessão. Para
reprodução, informe `session_origin_at` no endpoint
`fhir-subscription`: esse é o horário correspondente ao início da linha
temporal do vídeo; o deslocamento `start` da mídia é somado ao intervalo. O
backend rejeita eventos anteriores à origem e eventos além do relógio de mídia
analisado. A rota HTTP `/samples` exige `elapsed_seconds` explícito e não usa
essa conversão.

O teste E2E de câmera envia um Bundle FHIR sintético autenticado, verifica a
conversão do horário e a associação à evidência de mídia da mesma sessão, e
confirma a entrega do evento genérico ao webhook local sintético. Isso verifica
integração de software, não fonte institucional, significado clínico ou
atendimento por uma equipe.

## Webhook opcional

`ALERT_WEBHOOK_ENABLED=false` é o padrão. Quando explicitamente habilitado,
configure também `ALERT_WEBHOOK_URL` HTTPS e `ALERT_WEBHOOK_BEARER_TOKEN`.
Alertas críticos confirmados de imagem/fala e eventos de revisão da ingestão
autenticada HTTP/FHIR entram em `webhook_outbox`. O worker envia uma mensagem
genérica sem identificadores de pacientes nem transcrição, usando Bearer e
`Idempotency-Key`. Não segue redirecionamentos nem envia dentro da transação.

`GET /api/notifications/status` expõe configuração, saúde do worker e as
últimas entregas. `POST /api/notifications/{id}/retry` reprograma uma entrega
falha. Falhas transitórias são tentadas até cinco vezes; a entrega é pelo menos
uma vez e o receptor deve deduplicar. Um 2xx não garante contato com a equipe
ou atendimento. Desative o webhook até existir destinatário autorizado e
verificado; o único teste ponta a ponta atual usa receptor sintético em
loopback. Execute somente um processo Uvicorn para não duplicar workers.
O [README principal](../README.md#webhook-opcional-de-alertas) descreve
limites, retomada, privacidade e comportamento de falhas.

Uploads são limitados a JPEG de 10 MB (16 megapixels), WAV de 2 MB (até 30 s),
30 minutos por sessão e 10.800 frames. Com `record: false`, o backend guarda
somente estado e histórico no SQLite, não retém frames ou áudio. Com
`record: true`, exige FFmpeg, gera um MP4 com cerca original, vídeo e áudio
capturados e o adiciona à biblioteca de vídeos de leito. Falhas ao finalizar
preservam os arquivos temporários específicos da sessão para permitir nova
tentativa de encerramento.
