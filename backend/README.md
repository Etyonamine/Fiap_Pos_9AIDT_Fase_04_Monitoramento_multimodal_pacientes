# Backend de monitoramento

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
