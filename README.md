# Fiap_Pos_9AIDT_Fase_04_Monitoramento_multimodal_pacientes
## Laboratório de análise de vídeo e postura

Feature 1 do Tech Challenge: arquivos clínicos gravados, YOLOv8 Pose, cerca
virtual, telemetria e relatório de desvios. Interface Angular em três colunas
inspirada nos dashboards em `desenvolvimento/imagem/topico 1`.

## Executar localmente

Requer Python 3.11+, Node compatível com Angular 21 e FFmpeg com `libx264`.
Use arquivos autorizados e desidentificados. Não há envio de vídeos a serviços
externos, nem dependência de RTSP. A análise de áudio de leito envia
somente os trechos de áudio já reproduzidos e sua transcrição ao Azure durante a reprodução,
sem confirmação adicional na interface. Use apenas gravações adequadas para esse envio.

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

Abra `http://localhost:4200/video` para fisioterapia ou
`http://localhost:4200/telemetry` para monitoramento de leitos e alertas.
O proxy Angular encaminha `/api` ao FastAPI.
Em produção, configure o mesmo encaminhamento no servidor HTTP, incluindo
suporte a Range e limite de upload de 500 MB. `YOLO_MODEL_PATH` e
`VIDEO_DATA_DIR` permitem definir caminhos alternativos. Os padrões são
`backend/models/yolov8n-pose.pt` e `backend/data`, independentemente da pasta
usada para iniciar o servidor. Caminhos relativos nessas variáveis também
são resolvidos a partir de `backend`; caminhos absolutos são preservados.
O erro 503 de pesos ausentes mostra o caminho exato verificado. Se o arquivo
já estiver no caminho padrão, reinicie o backend com esta correção; não é
necessário baixar os pesos novamente.
Confira também `YOLO_MODEL_PATH` em `backend/.env`: use
`models/yolov8n-pose.pt`, não `yolov8n.pt` (modelo de detecção, sem pose).

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
processados automaticamente e aparecem na biblioteca. Arquivos na pasta `data`
da raiz não são importados automaticamente: selecione-os no upload.
Exemplos de fisioterapia carregados automaticamente não possuem postura informada,
portanto não geram alertas de postura; envie o arquivo pela interface para selecioná-la.
Também é possível enviar arquivos pela interface. A página **Análise de vídeos
de fisioterapia** (`/video`) aceita somente exercícios de fisioterapia;
**Telemetria e anomalias** (`/telemetry`) reúne as gravações de leito,
monitoramento de movimento e áudio, cerca virtual, alertas, relatórios e
histórico de atendimento. Cada biblioteca mostra apenas a modalidade da sua
página, sem seletor; arquivos existentes mantêm sua modalidade.

Na fisioterapia, escolha **em pé**, **sentado**, **deitado** ou **híbrido** antes
de escolher o arquivo. Para híbridos, use a prévia local ou informe manualmente
início e fim em segundos para cada intervalo, em ordem e sem sobreposição. O início
é inclusivo e o fim exclusivo; deixe transições sem marcação quando a postura não
for clara. Lacunas são inconclusivas e não geram alertas de postura. Se o navegador
não reproduzir o formato original, os tempos ainda podem ser digitados; o servidor
confere os intervalos contra a duração do vídeo convertido. Para corrigir as
marcações de uma análise já enviada, reenvie o vídeo.

Na telemetria, o cartão **Leito 1** pode abrir uma prévia da câmera
do computador, mediante permissão do navegador. Essa prévia usa apenas vídeo no
dispositivo: não é enviada ao servidor, não executa YOLO, não gera alertas e não
grava nem analisa áudio. Para obter análise de pose e eventos, envie uma gravação
de vídeo.

As seções **Sinais vitais** (batimentos, pressão e oxigenação) e **Evolução de
prescrições** indicam explicitamente a ausência de integração. Não consultam
sensores ou prescrições nem geram alertas desses eixos. O fluxo funcional de
alertas permanece restrito ao replay de leitos; não há notificação externa da
equipe médica. Ao navegar entre módulos, a câmera e a sessão anterior são encerradas.

1. `POST /api/videos` recebe multipart `file` e `mode` (`bed` ou `fisio`),
   limita o tamanho a 500 MB e retorna HTTP 202 com o identificador da análise.
   Para `fisio`, exige também `posture`, uma string JSON, por exemplo
   `{"type":"lying","intervals":[]}` ou
   `{"type":"hybrid","intervals":[{"start":0,"end":2.5,"posture":"standing"},{"start":3,"end":6,"posture":"lying"}]}`.
   As posturas aceitas são `standing`, `sitting` e `lying`; no híbrido, os
   intervalos são sequenciais, não sobrepostos, e medidos em segundos na linha
   do tempo do vídeo. Erros de duração são informados no estado de processamento.
2. Um worker serial em segundo plano converte MP4/AVI/MOV/WebM em H.264/AAC
   com FFmpeg, normalizando a linha do tempo para 25 fps. No modo **leito**,
   isso apenas prepara o arquivo: não executa YOLO nem Azure no upload.
   No modo **fisioterapia**, YOLOv8 Pose processa
   **todos os frames**, armazenando pessoas, caixas e 17 keypoints normalizados
   em SQLite, com índice composto `(video_id, timestamp)`.
3. `GET /api/videos/{id}` informa fila, progresso, conclusão ou erro. A cópia
   original temporária é removida após processamento; o MP4 e o SQLite persistem
   em `backend/data` para replay. Reinícios marcam trabalhos interrompidos como
   falha; reenvie o arquivo para tentar novamente.
4. O player HTML5 oferece play/pause, áudio, tela cheia e scrubbing nativos.
   No modo leito, a reprodução cria uma sessão de monitoramento descrita abaixo.
   Na fisioterapia, o frontend consulta `GET /api/videos/{id}/frame?timestamp=...` pelo tempo
   exibido; o backend retorna o frame correspondente, nunca um frame futuro.
   Seeks cancelam respostas antigas e limpam o overlay. Metadados atrasados
   não são desenhados sobre outro frame; sob latência alta o overlay pode ficar
   temporariamente vazio em vez de exibir uma pose incorreta.
5. Na fisioterapia, `GET /api/videos/{id}/events` fornece a tabela cronológica. O log acompanha
   avanços e retrocessos; clicar no tempo navega ao evento.
   `PUT /api/videos/{id}/fence` salva a cerca retangular normalizada e recalcula
   os eventos de toda a gravação sem repetir a inferência.
6. `GET /api/videos/{id}/report` gera o relatório JSON automático, disponível
   pelo botão **Relatório**, com arquivo, modelo, eventos, severidades e ressalvas.
   No modo leito, o botão baixa o relatório da sessão atual, não o histórico pré-analisado.

### Monitoramento de leito durante a reprodução

O fluxo da demonstração é **carregar → reproduzir → analisar → alertar**.
Selecionar um vídeo pronto não carrega suas detecções ou transcrições antigas.
Somente **Reproduzir** inicia uma sessão, a partir da posição atual, sem confirmação
adicional para Azure. A câmera de prévia continua sem gravar nem enviar áudio.

O player envia a posição reproduzida; o servidor infere todos os frames entre
o último frame analisado e essa posição, **sem inferir frames futuros**. Cada
requisição processa até 25 frames, mas as seguintes continuam do próximo frame,
sem descartar frames intermediários. A tela informa a contagem real e o atraso
entre a reprodução e o processamento. Se CPU/rede não sustentarem 25 fps,
a análise fica atrasada: não é uma garantia de execução em tempo real estrito.
O overlay só é desenhado quando corresponde ao frame exibido.

Áudio usa **Speech contínuo em streaming**, independente do progresso do YOLO.
Um decoder FFmpeg por passagem fornece PCM mono de 16 bits a 16 kHz; apenas
amostras até a posição já reproduzida são encaminhadas ao `PushAudioInputStream`
do Azure, em pequenos envios de até 100 ms. Não é necessário acumular 3 segundos,
reiniciar Speech a cada bloco ou aguardar o fim do vídeo. A conexão é reutilizada
durante a reprodução contínua. O frontend consulta imagem e áudio separadamente,
a cada 100 ms, sem requisições sobrepostas em cada caminho.

Falas finais reconhecidas em `pt-BR` atualizam imediatamente a transcrição e
as regras de alerta. Sentimento e termos-chave são calculados em segundo plano:
uma resposta lenta de Language não atrasa esses alertas nem o próximo reconhecimento.
No máximo uma análise Language por passagem fica em execução/fila no executor;
as demais falas reconhecidas aguardam sua vez sem bloquear Speech. A transcrição
provisória também pode antecipar **avisos críticos provisórios**, identificados
como **PROVISÓRIO** na faixa de atendimento e no registro. A cada revisão do texto,
esses avisos são substituídos; se o gatilho desaparecer ou for negado, são retirados.
O resultado final confirma o gatilho ou retira o aviso. Avisos de imagem e falas
finais anteriores são preservados. Pode haver **falso positivo temporário**:
o reconhecimento provisório pode mudar. O silêncio de segmentação do Speech
é ajustado para 300 ms; isso não é uma promessa de latência total de 300 ms.
Rede, inicialização da conexão e segmentação da fala ainda causam atraso.

Pausar/finalizar fecha a entrada de Speech e conclui apenas a cauda já
reproduzida; retomar abre uma nova conexão a partir da primeira amostra ainda
não enviada, sem repetir áudio nem analisar o futuro. O painel distingue
**áudio enviado** de **fala reconhecida**, e indica Language pendente por trecho.
O timestamp do evento é do trecho reconhecido, não de cada palavra.

Silêncio é normal, não um gatilho. Vídeo sem faixa de áudio, configuração Speech
ausente ou falha no reconhecimento mostram erro explícito, sem impedir YOLO.
Após falha Speech, retroceda/reinicie a reprodução para tentar novamente depois
de corrigir a causa. Configuração ausente ou falha Language aparece no trecho,
mas não interrompe Speech e preserva a fala e seus alertas.

Menções não negadas como “dor no peito” e “falta de ar” geram eventos críticos;
pedidos explícitos como “socorro”, “me ajuda”, “me ajude”, “preciso de ajuda”
e “precisando de ajuda” também ativam o atendimento imediato simulado.
“Cansaço” e “tontura” geram avisos. As regras são heurísticas, sem identificação
do falante. O tempo do alerta é o início do **trecho reconhecido**, não o instante
exato de cada palavra. Os eventos aparecem no registro e no relatório da sessão. Silêncio, sentimento
negativo ou baixa energia isolados não são tratados como emergência clínica.
Eventos críticos de fala (inclusive provisórios identificados) ou cerca ativam **Alerta de atendimento imediato · Leito 1**
somente depois de serem detectados durante a reprodução, com eventual atraso.
O aviso é uma solicitação de atendimento **simulada**. Pausar mantém os alertas
já confirmados; avisos provisórios podem ser corrigidos ao concluir o trecho.
Buscar outro instante (inclusive retroceder) encerra a sessão e
limpa seus alertas; ao reproduzir novamente, nova inferência e novas chamadas
Azure permitem **disparar novamente** o mesmo gatilho. Avançar por seek não
analisa o intervalo pulado. Alterar a cerca também encerra a sessão; a configuração
vale na próxima reprodução, sem antecipar resultados. Não há notificação externa,
chamada médica ou captura de microfone ao vivo.
Ausência de alerta não exclui risco.

### Log de alertas, intenção de atendimento e bip

Cada alerta crítico da passagem (imagem ou fala, inclusive provisória) é salvo
automaticamente no SQLite em `monitor_alerts`. O log `monitor_alert_log` preserva
disparos, confirmações, retiradas e reativações, com data/hora UTC do servidor,
sessão, origem, tipo e posição no vídeo. Consultas repetidas não duplicam o disparo.
Um aviso provisório retirado não é apagado do histórico.

Na faixa vermelha, **Vou atender de imediato** registra a intenção de atender
os alertas ativos ainda não reconhecidos. A confirmação mostra data/hora local
somente após sucesso do servidor; cliques repetidos não duplicam o registro.
Novos alertas habilitam o botão novamente. Isso **não comprova atendimento
realizado**, não identifica um profissional (o laboratório não tem autenticação)
e não aciona equipe externa. A intenção registrada em um aviso provisório continua
no histórico mesmo se o reconhecimento posteriormente retirar esse aviso.

Enquanto houver alerta crítico ativo sem intenção de atendimento registrada,
um bip curto de 880 Hz repete **a cada segundo**, inclusive com o vídeo pausado.
O bip para após o servidor confirmar **Vou atender de imediato** para todos os
alertas ativos; falha no registro mantém o bip. Novos alertas reiniciam o som.
Consultas e confirmações da mesma fala não criam temporizadores extras.
Retirar o único aviso provisório, encerrar a passagem, buscar outro instante
ou sair da tela também interrompe o som, pois não há mais alerta ativo nessa passagem.
O áudio do alerta é separado do volume/mute do vídeo. O navegador pode exigir
interação para liberar Web Audio: use **Ativar som dos alertas**; falhas são
mostradas explicitamente e não impedem o aviso visual ou o log. O som depende
também do volume e da saída de áudio do dispositivo.

**Histórico de alertas e atendimento → Consultar / atualizar histórico** mostra
até 200 entradas mais recentes da gravação, incluindo passagens anteriores.
O log sobrevive a reload/reinício e também integra o relatório da sessão (até
200 entradas recentes). São logs locais de simulação, sujeitos à mesma política
de retenção e proteção de dados do SQLite.

APIs da demonstração:

- `POST /api/videos/{id}/monitor` com `{"timestamp": 0}` cria a passagem sem inferir.
- `POST /api/videos/{id}/monitor/{session}/advance` com `timestamp` e `flush_audio`
  processa somente frames alcançados; `flush_audio` não é usado nesse caminho.
- `POST /api/videos/{id}/monitor/{session}/audio` com `timestamp` e `flush_audio`
  atualiza a fronteira de áudio já reproduzido e retorna fala/eventos sem esperar YOLO
  ou Language. `flush_audio: true` finaliza somente o trecho já enviado ao pausar.
- `DELETE /api/videos/{id}/monitor/{session}` encerra a passagem e libera o decoder.
- `GET /api/videos/{id}/monitor/{session}/report` retorna o snapshot persistido,
  com contagem de frames, eventos, trechos de texto e `alert_log`, mesmo após encerrar.
- `POST /api/videos/{id}/monitor/{session}/acknowledge`, com `{"alert_ids": ["..."]}`,
  registra idempotentemente intenção de atendimento imediato para até 100 alertas
  ativos da sessão. IDs inválidos, de outra sessão ou retirados rejeitam a operação inteira.
- `GET /api/videos/{id}/alert-log` lista as últimas 200 transições persistidas da gravação.

Resultados persistem em `monitor_sessions` no SQLite; o streaming usa um pipe PCM,
sem criar WAVs intermediários. Encerrar a sessão interrompe o decoder e Speech,
descarta retornos tardios e marca análises Language pendentes como descartadas.
Até 8 sessões simultâneas são aceitas; sessões sem uso por 30 minutos são encerradas
ao abrir outra. Reiniciar o backend exige nova sessão de reprodução; relatórios
anteriores permanecem disponíveis. O endpoint antigo de análise integral de áudio
de leito retorna 409, orientando reproduzir o vídeo. Resultados integrais antigos
continuam disponíveis para compatibilidade, mas **não alimentam a demonstração**.
Fisioterapia e o módulo de voz mantêm seus fluxos anteriores. Repetir uma passagem
faz novas chamadas ao Azure e pode gerar novos custos.

### Teste com `data/leito_caindo_cama.mp4`

Envie esse arquivo no modo **Monitoramento de leitos**. A validação local com
os pesos existentes processou **250 frames a 25 fps (10 s)** e extraiu
**10,027 s de áudio**. A cerca padrão não gera saída nesse vídeo, pois abrange
quase toda a imagem, incluindo o chão onde a pessoa termina.

Para demonstrar a saída, em **Ajustar cerca virtual**, configure **X 45%,
Y 20%, largura 45%, altura 52%** e salve. Reduza primeiro largura e altura para
liberar os ajustes de X e Y. Nesse teste, a área delimitada gerou **Saída da cerca virtual**
crítica em **00:07.40**. É uma configuração deste enquadramento, não um limiar
clínico nem uma detecção automática dos limites da cama. Ajuste cada câmera e
revise os quadris detectados: cobertas, oclusões e detecções duplicadas podem
alterar o acompanhamento. Na validação manual pelo navegador, não houve alerta
antes de reproduzir. Durante a reprodução, Azure reconheceu “AI Socorro, alguém
me ajuda por favor?” e ativou o atendimento imediato. Retroceder limpou o aviso;
reproduzir novamente voltou a dispará-lo. Os testes automatizados substituem
as chamadas ao provedor, sem enviar esse vídeo ao Azure.

Em um ensaio local do streaming com esse áudio enviado no ritmo da reprodução,
o primeiro aviso provisório de “socorro” chegou em **2,97 s** desde o início;
a fala final chegou em **8,62 s**, ainda com Language pendente. Nenhuma amostra
futura foi enviada, e o teste de áudio funcionou sem avançar nenhum frame do YOLO.
Esses tempos são observações de uma execução, não uma garantia de latência.

### Interpretação e limites

Os ângulos são medidos em coordenadas de imagem 2D, usando keypoints com
confiança ≥ 0,5; confiança não garante identificação correta das articulações.
Na fisioterapia, para posturas informadas em pé ou sentado, inclinação de tronco
em relação à vertical > 35° gera aviso por padrão. Na posição deitada, essa
medida continua visível, mas não gera aviso de tronco e não mede hiperextensão
lombar. Em qualquer postura informada, ângulo interno de flexão do joelho < 60°
gera aviso por padrão. Os limites são configuráveis, não individualizados ao
exercício nem clinicamente validados. O ângulo de flexão não mede valgo; rotação,
arqueamento lombar e ritmo também não são avaliados. A postura é informada pelo
usuário, não detectada automaticamente. Lacunas de vídeos híbridos não geram
alertas de postura. Vídeos antigos sem seleção preservam a regra anterior, que
alerta mesmo em posição deitada, e são identificados na interface.
Métricas e alertas de postura usam
a pessoa acompanhada pela cerca virtual, não a primeira detecção; se nenhum
alvo ou keypoints suficientes estiverem disponíveis, a tela informa que a análise
é inconclusiva e não inventa um alerta. Com a cerca desativada, o alvo de postura
é a maior pessoa detectada e continua sendo acompanhado. As cercas padrão dos
modos leito e fisioterapia se estendem até a borda inferior do vídeo; no modo
fisioterapia, use **Aplicar margem para avanço** para também ampliar a margem superior.
Vídeos de leito salvos com o limite inferior antigo são atualizados na
inicialização e têm os eventos recalculados. A cerca acompanha uma pessoa já detectada dentro da área,
associando-a entre frames pela proximidade da caixa; pessoas que entram depois
não geram saídas da cerca para essa pessoa. Se o acompanhamento não puder ser
associado com confiança espacial, nenhum evento de saída é inferido naquele
frame. A saída do ponto médio dos quadris da pessoa acompanhada gera um evento
crítico em ambos os modos. Os logs registram o início de cada ocorrência, sem
repetir o mesmo aviso em todos os frames consecutivos. Ao salvar um novo ajuste,
os frames e eventos pré-analisados existentes são recalculados com o acompanhamento
atualizado; registros anteriores também são migrados e recalculados ao iniciar
o backend. Isso não antecipa alertas na demonstração de leito: cada passagem usa
somente as novas inferências realizadas durante sua reprodução.

Essas regras são heurísticas de demonstração, **não validadas clinicamente**:
agachamentos profundos e inclinações podem ser intencionais. Saída da cerca não
é detecção comprovada de queda. Não há diagnóstico, identificação do paciente
ou envio de alertas à equipe médica nesta feature. O acompanhamento por caixa
é apenas espacial e não estabelece identidade entre frames.

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

Na interface, marque a autorização para habilitar a seleção e importação do arquivo.
A transcrição e análise no Azure iniciam automaticamente assim que a conversão
termina, desde que a autorização esteja marcada nesse momento. Caso não esteja,
a análise pode ser iniciada manualmente após nova confirmação.
O resumo apresenta o estado e os achados disponíveis da consulta selecionada;
não é diagnóstico nem envia alertas à equipe. Para repetir uma análise concluída
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