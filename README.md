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

No Windows, a partir da raiz do repositório, instale as dependências no mesmo
ambiente virtual usado para iniciar o backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
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

No Windows, inicie-o com `..\.venv\Scripts\python.exe -m uvicorn app.main:app
--host 127.0.0.1 --port 8000`, garantindo que o SDK Speech seja instalado nesse
mesmo Python.

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
Ao sair ou atualizar a página, o frontend solicita o fechamento normal do socket
e cancela novas tentativas; ao restaurar a página pelo histórico, abre uma nova
conexão. Um `ws proxy error: write ECONNRESET` isolado durante a atualização
pode ocorrer quando o navegador interrompe a conexão antes de concluir o
fechamento. Se o indicador voltar a **ATIVO**, esse log não indica falha na
análise. Se persistir sem atualizar a página ou o indicador permanecer
**NÃO CONECTADO**, confira se o FastAPI está em `127.0.0.1:8000`, examine seus
logs e confirme a instalação de `uvicorn[standard]`; não desative o proxy
WebSocket para ocultar o erro.
O indicador não usa respostas HTTP nem conectividade de rede como substitutos
da conexão WebSocket; **ATIVO** não valida os recursos Azure de voz nem significa
que os sensores demonstrativos estejam integrados.

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

## Módulo de áudio: consultas, transcrição e linguagem

Abra `http://localhost:4200/voice`. O módulo aceita WAV, MP3, M4A, OGG,
FLAC, WebM e AAC de até **100 MB e 30 minutos**. A importação não exige Azure:
FFmpeg converte para WAV PCM mono de 16 bits a 16 kHz, calcula energia e
forma de onda reais e disponibiliza reprodução HTML5 com busca temporal.
Arquivos sem áudio decodificável ou acima dos limites geram erro explícito;
não são analisados parcialmente nem substituídos por exemplos.

Copie `backend/.env.example` para `backend/.env` e preencha com os valores dos
seus recursos, sem publicar o arquivo:

```dotenv
AZURE_SPEECH_KEY=chave_do_recurso_speech
AZURE_SPEECH_REGION=eastus
AZURE_LANGUAGE_KEY=chave_do_recurso_language
AZURE_LANGUAGE_ENDPOINT=https://nome-do-recurso.cognitiveservices.azure.com
```

O backend carrega esse arquivo independentemente do diretório de execução;
variáveis de ambiente já definidas têm prioridade. Os nomes legados
`AZURE_TEXT_ANALYTICS_KEY` e `AZURE_TEXT_ANALYTICS_ENDPOINT` também são aceitos,
com prioridade para `AZURE_LANGUAGE_*`. Use a região do recurso Speech e a
chave/endpoint do mesmo recurso Language (Text Analytics). Reinicie o backend
após configurar. As credenciais não são enviadas ao navegador; o indicador de
configuração não comprova conexão ou quota.

### Erro 503 ao iniciar a análise

`206 Partial Content` em `/media` é uma resposta normal à reprodução com Range.
Já `503 Service Unavailable` em `POST /api/audios/{id}/analyze` indica que a
validação local da configuração Azure falhou **antes** de iniciar a transcrição.
Confira o campo `detail` da resposta no painel Network do navegador ou a mensagem
`Análise do áudio ... não iniciada` no log do backend. Para consultar a mesma
validação sem enviar áudio ao Azure:

```bash
curl http://127.0.0.1:8000/api/audios/configuration
```

Se `configured` for `false`, o campo `message` informa as variáveis ausentes
ou inválidas. Preencha `backend/.env` com credenciais reais, não com os
marcadores de `.env.example`. São necessários tanto Speech quanto Language
para iniciar a análise completa. `AZURE_SPEECH_REGION` deve conter apenas a
região (por exemplo, `eastus`), não uma URL; `AZURE_LANGUAGE_ENDPOINT` deve ser
o endpoint HTTPS do recurso Language. Confira também variáveis exportadas no
terminal ou definidas na IDE, pois elas prevalecem sobre o arquivo `.env`.
Reinicie o backend e tente novamente com o áudio já importado; não é necessário
reenviá-lo. Não compartilhe chaves ao enviar informações de diagnóstico.

### Transcrição e resultados

Marque a autorização antes de importar para iniciar automaticamente a transcrição e
análise no Azure assim que a conversão do áudio terminar. Sem autorização marcada,
o áudio permanece apenas importado e reproduzível; a análise pode ser iniciada
manualmente depois de confirmar a autorização. Para repetir uma análise concluída
ou tentar novamente após uma falha, use a ação correspondente no áudio já importado.
O SDK Speech usa reconhecimento contínuo em `pt-BR`, sem a restrição de 60 s
do endpoint curto utilizado na referência antiga. Trechos reconhecidos têm
timestamp e confiança reais quando fornecida pelo Azure; clique no tempo para
navegar no player. Não há diarização ou identificação de paciente/médico.
Azure Text Analytics extrai termos-chave e sentimento do texto, dividido em
trechos de até 4.500 caracteres e lotes de até 10 documentos. Os scores são
ponderados pelo comprimento dos trechos; rótulos divergentes produzem “Misto”.
Isso não mede emoção pela voz nem estabelece estado clínico.

Regras locais, inspiradas no módulo antigo, sinalizam menções como falta de ar,
dor no peito, dispneia, cansaço e fadiga e distinguem negação heurística. Essas
regras **não são reconhecimento médico do Azure**, não identificam o falante e
podem errar em perguntas, hipóteses, histórico ou negações complexas.
Indicadores acústicos usam janelas de 100 ms: energia RMS normalizada < 0,02,
proporção de baixa energia ≥ 40%, trecho de baixa energia ≥ 2 s e saturação
≥ 1% das amostras (amplitude absoluta ≥ 32760). Não são detectores validados
de fadiga ou dificuldade respiratória. Em gravações de pelo menos 30 s, compara
também RMS das janelas acima de 0,02 no primeiro e no último terço (mínimo de
10 janelas em cada): redução de pelo menos 6 dB gera aviso de variação de
intensidade, que também pode refletir microfone/distância. Detecção clínica
exigiria avaliação e validação com dados apropriados. Áudio sem limiares
ultrapassados não comprova normalidade.

`POST /api/audios` importa em segundo plano; `GET /api/audios` lista a biblioteca;
`GET /api/audios/{id}` informa estado/erro/resultados; `/media` suporta Range;
`POST /api/audios/{id}/analyze` inicia Azure; `DELETE /api/audios/{id}` remove
gravação e resultados quando não há processamento em curso.
O frontend acompanha os estados `importing`, `uploaded`, `queued`, `analyzing`,
`ready` e `failed`. Se Language falhar após Speech, preserva a transcrição e
mostra erro, sem sentimento inventado. Reinícios marcam tarefas interrompidas
como falha; reanalise o WAV existente ou reimporte se a conversão não terminou.

WAV e resultados persistem em `backend/data` (ou `VIDEO_DATA_DIR`) e na tabela
`audios` do SQLite existente. A cópia original temporária é removida após
conversão. Use **Excluir gravação e resultados** conforme a política de retenção;
isso não controla retenção do provedor Azure nem equivale a apagamento forense.
Configure privacidade, região e retenção nos seus recursos Azure antes de usar
gravações reais. O laboratório continua local/monousuário, sem autenticação;
não o exponha publicamente. Speech/Language podem gerar custos.

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