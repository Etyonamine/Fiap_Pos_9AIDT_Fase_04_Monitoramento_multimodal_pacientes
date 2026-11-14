# Backend de monitoramento

## Testes

O ambiente Windows de CI usa `requirements-test.lock.txt` (Python 3.14);
`requirements-test.txt` declara as dependências de testes, incluindo pytest-cov.
Execute a partir de `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests --cov=app --cov=evaluation --cov-branch --cov-report=json:coverage.json --cov-report=xml:coverage.xml -q
.\.venv\Scripts\python.exe -m evaluation demo --output evaluation-report.json
```

Os testes bloqueiam rede externa em sockets Python e removem credenciais Azure
herdadas; somente integrações simuladas são usadas. FFmpeg e SQLite são reais.
Além das regras de vídeo/voz/incidentes, há casos adversos de câmera e testes de
concorrência, orçamento de latência local e memória de polling. O helper SQLite
fecha conexões ao sair de `with`, preservando commit/rollback e liberando arquivos.
O servidor E2E isolado também remove credenciais Azure, bloqueia sockets externos
e substitui YOLO e Speech; as rotas HTTP, FFmpeg e SQLite continuam reais.
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

Uploads são limitados a JPEG de 10 MB (16 megapixels), WAV de 2 MB (até 30 s),
30 minutos por sessão e 10.800 frames. Com `record: false`, o backend guarda
somente estado e histórico no SQLite, não retém frames ou áudio. Com
`record: true`, exige FFmpeg, gera um MP4 com cerca original, vídeo e áudio
capturados e o adiciona à biblioteca de vídeos de leito. Falhas ao finalizar
preservam os arquivos temporários específicos da sessão para permitir nova
tentativa de encerramento.
