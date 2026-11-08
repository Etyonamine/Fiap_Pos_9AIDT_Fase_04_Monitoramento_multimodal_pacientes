# Fiap_Pos_9AIDT_Fase_04_Monitoramento_multimodal_pacientes
## Laboratório de análise de vídeo e postura

Feature 1 do Tech Challenge: arquivos clínicos gravados, YOLOv8 Pose, cerca
virtual, telemetria e relatório de desvios. Interface Angular em três colunas
inspirada nos dashboards em `desenvolvimento/imagem/topico 1`.

## Executar localmente

Requer Python 3.11+, Node compatível com Angular 21 e FFmpeg com `libx264`.
Use arquivos autorizados e desidentificados. Não há envio de vídeos a serviços
externos, nem dependência de RTSP.

```bash
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
mkdir -p backend/models backend/data/samples
```

Para ambientes sem GPU, instale primeiro PyTorch e torchvision pelo índice CPU
oficial (`https://download.pytorch.org/whl/cpu`). Instale FFmpeg pelo gerenciador
de pacotes do sistema. Disponibilize pesos **YOLOv8 Pose** de fonte confiável em
`backend/models/yolov8n-pose.pt`; observe a licença da Ultralytics e dos pesos.
O servidor não baixa pesos automaticamente.

```bash
cd backend
../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Em outro terminal:

```bash
cd frontend
npm ci
npm start
```

Abra `http://localhost:4200/video`. O proxy Angular encaminha `/api` ao FastAPI.
Em produção, configure o mesmo encaminhamento no servidor HTTP, incluindo
suporte a Range e limite de upload de 500 MB. `YOLO_MODEL_PATH` e
`VIDEO_DATA_DIR` permitem definir caminhos absolutos alternativos.

O indicador superior acompanha uma conexão WebSocket em `/api/ws` (usa `wss`
sob HTTPS). Somente a abertura desse socket exibe **SISTEMA: ATIVO**; enquanto
conecta, após erro ou desconexão, exibe **SISTEMA: NÃO CONECTADO** em vermelho,
com nova tentativa a cada 5 segundos após fechamento ou falha de criação.
O backend implementa `/api/ws` como canal de disponibilidade; ele não transmite
análises, áudio ou alertas clínicos. As dependências `uvicorn[standard]` incluem
suporte a WebSocket. Em produção, encaminhe também o upgrade de `/api/ws`;
o proxy de desenvolvimento já encaminha `/api/**`, incluindo esse canal.
Após atualizar as dependências e o proxy, reinicie o backend e o `npm start`.
O indicador não usa respostas HTTP nem conectividade de rede como substitutos
da conexão WebSocket; **ATIVO** não significa que os módulos demonstrativos
de voz e sensores estejam integrados.

## Demonstração e fluxo

Coloque vídeos reais em `backend/data/samples` antes de iniciar o backend, por
exemplo `bed01_fall_event.mp4` e `physio_squat_high_risk.avi`. Prefixos `physio`
ou `fisio` selecionam fisioterapia; os demais selecionam leito. Exemplos são
processados automaticamente e aparecem na biblioteca. O repositório não inclui
vídeos clínicos nem pesos; a biblioteca vazia informa como adicioná-los.
Também é possível enviar arquivos pela interface, selecionando o modo antes do
upload. O modo de um arquivo já analisado não muda ao alternar o seletor.

Na tela de monitoramento, escolha primeiro **Monitoramento de leitos** ou
**Análise de fisioterapia**. O cartão **Leito 1** pode abrir uma prévia da câmera
do computador, mediante permissão do navegador. Essa prévia usa apenas vídeo no
dispositivo: não é enviada ao servidor, não executa YOLO, não gera alertas e não
grava nem analisa áudio. Para obter análise de pose e eventos, envie uma gravação
de vídeo.

1. `POST /api/videos` recebe multipart `file` e `mode` (`bed` ou `fisio`),
   limita o tamanho a 500 MB e retorna HTTP 202 com o identificador da análise.
2. Um worker serial em segundo plano converte MP4/AVI/MOV/WebM em H.264/AAC
   com FFmpeg, normalizando a linha do tempo para 25 fps. YOLOv8 Pose processa
   **todos os frames**, armazenando pessoas, caixas e 17 keypoints normalizados
   em SQLite, com índice composto `(video_id, timestamp)`.
3. `GET /api/videos/{id}` informa fila, progresso, conclusão ou erro. A cópia
   original temporária é removida após processamento; o MP4 e o SQLite persistem
   em `backend/data` para replay. Reinícios marcam trabalhos interrompidos como
   falha; reenvie o arquivo para tentar novamente.
4. O player HTML5 oferece play/pause, áudio, tela cheia e scrubbing nativos.
   O frontend consulta `GET /api/videos/{id}/frame?timestamp=...` pelo tempo
   exibido; o backend retorna o frame correspondente, nunca um frame futuro.
   Seeks cancelam respostas antigas e limpam o overlay. Metadados atrasados
   não são desenhados sobre outro frame; sob latência alta o overlay pode ficar
   temporariamente vazio em vez de exibir uma pose incorreta.
5. `GET /api/videos/{id}/events` fornece a tabela cronológica. O log acompanha
   avanços e retrocessos; clicar no tempo navega ao evento.
   `PUT /api/videos/{id}/fence` salva a cerca retangular normalizada e recalcula
   os eventos de toda a gravação sem repetir a inferência.
6. `GET /api/videos/{id}/report` gera o relatório JSON automático, disponível
   pelo botão **Relatório**, com arquivo, modelo, eventos, severidades e ressalvas.

### Interpretação e limites

Os ângulos são medidos em coordenadas de imagem 2D, usando keypoints com
confiança ≥ 0,5. Na fisioterapia, inclinação de tronco > 35° e < 60° e flexão
de joelho < 60° geram avisos. Troncos a partir de 60° em relação à vertical
são tratados como posição horizontal/deitada e não geram alerta de inclinação;
o ângulo continua disponível na telemetria. As cercas padrão dos modos leito e
fisioterapia se estendem até a borda inferior do vídeo; no modo fisioterapia,
use **Aplicar margem para avanço** para também ampliar a margem superior.
Vídeos de leito salvos com o limite inferior antigo são atualizados na
inicialização e têm os eventos recalculados. A cerca acompanha uma pessoa já detectada dentro da área,
associando-a entre frames pela proximidade da caixa; pessoas que entram depois
não geram saídas da cerca para essa pessoa. Se o acompanhamento não puder ser
associado com confiança espacial, nenhum evento de saída é inferido naquele
frame. A saída do ponto médio dos quadris da pessoa acompanhada gera um evento
crítico em ambos os modos. Os logs registram o início de cada ocorrência, sem
repetir o mesmo aviso em todos os frames consecutivos. Ao salvar um novo ajuste,
os frames e eventos existentes são recalculados com o acompanhamento atualizado;
registros anteriores também são migrados e recalculados ao iniciar o backend.

Essas regras são heurísticas de demonstração, **não validadas clinicamente**:
agachamentos profundos e inclinações podem ser intencionais. Saída da cerca não
é detecção comprovada de queda. Não há diagnóstico, identificação do paciente
ou envio de alertas à equipe médica nesta feature. Os valores de telemetria
referem-se à primeira pessoa detectada e não estabelecem identidade entre frames.

Este laboratório é local e monousuário. Não o exponha publicamente sem
autenticação, autorização, quotas, política de retenção e proteção de dados.
Execute um único processo Uvicorn (sem `--workers`): a fila é local e serial.
Os arquivos convertidos e metadados devem ser removidos conforme a política de
retenção da instituição, com o servidor parado.

## Verificação

```bash
.venv/bin/python -m pytest backend/tests -q
cd frontend
npm test -- --watch=false
npm run build
```

Os testes de pipeline usam um modelo substituto explícito, mas conversão,
decodificação, Range HTTP e SQLite reais. A qualidade das predições deve ser
avaliada separadamente com os pesos e vídeos clínicos autorizados.