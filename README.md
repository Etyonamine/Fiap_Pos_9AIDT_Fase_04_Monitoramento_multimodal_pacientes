# Fiap_Pos_9AIDT_Fase_04_Monitoramento_multimodal_pacientes
## Laboratório de análise de vídeo e postura

Feature 1 do Tech Challenge: arquivos clínicos gravados, YOLOv8 Pose, cerca
virtual, telemetria e relatório de desvios. Interface Angular em três colunas
inspirada nos dashboards em `desenvolvimento/imagem/topico 1`.

## Qualidade, cobertura e avaliação de IA

A suíte separa testes de software de validação do modelo. Testes automatizados
não usam arquivos de pacientes nem chamam Azure. O backend remove credenciais
Azure, FHIR e webhook herdadas durante os testes e bloqueia conexões externas em
sockets Python; os provedores são simulados. FFmpeg, SQLite e os fluxos HTTP
locais continuam reais nos testes pertinentes.

### Como executar os testes no Windows

Os comandos abaixo usam **PowerShell**. Execute os blocos na ordem, na mesma
janela, e verifique se cada comando terminou sem erro antes de continuar.
Comece pela raiz do repositório; ajuste o caminho se o projeto estiver em outra
pasta:

```powershell
Set-Location 'D:\Fiap_Pos_9AIDT_Fase_04_Monitoramento_multimodal_pacientes'
$repo = (Get-Location).Path
```

**Pré-requisitos:** Python 3.14 e Node.js 22 (versões usadas no CI), npm e
FFmpeg/ffprobe disponíveis no `PATH`. O lock Python é um snapshot do ambiente
Windows/Python 3.14 validado pelo CI; não certifica outros ambientes.

**1. Preparar o ambiente**, na primeira execução ou após alterações nas
dependências. Se `backend\.venv` já existir e estiver configurado, não é
necessário recriá-lo. `npm ci` reinstala as dependências do frontend conforme
o lock versionado.

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-test.lock.txt
Set-Location "$repo\frontend"
npm ci
npx playwright install chromium
Set-Location $repo
```

**2. Backend:** execute todos os testes e gere os relatórios de cobertura.

```powershell
Set-Location "$repo\backend"
.\.venv\Scripts\python.exe -m pytest tests --cov=app --cov=evaluation --cov-branch --cov-report=json:coverage.json --cov-report=xml:coverage.xml -q
```

O resultado informa quantos testes passaram ou falharam. Os arquivos
`backend/coverage.json` e `backend/coverage.xml` são gerados novamente.

**3. Frontend:** execute os testes Angular com cobertura e, separadamente, os
testes do AudioWorklet.

```powershell
Set-Location "$repo\frontend"
npm run test:coverage
npm run test:worklet
```

**4. Testes de ponta a ponta:** ainda em `frontend`, execute os cenários no
Chromium. O Playwright inicia automaticamente servidores isolados de backend e
frontend nas portas 8011 e 4211; elas devem estar disponíveis. Não é necessário
iniciar a aplicação manualmente.

```powershell
npm run test:e2e
```

**5. Controle de cobertura:** volte à raiz antes de executar os scripts. Eles
leem os relatórios gerados nos passos 2 e 3, portanto execute ambos novamente
após alterações no código ou nos testes.

```powershell
Set-Location $repo
node .\scripts\check-coverage.mjs
node --test .\scripts\check-coverage.test.mjs
```

O primeiro comando mostra os módulos abaixo dos limites e os totais medidos.
O primeiro teste do segundo comando também depende desses relatórios: se
estiverem ausentes, desatualizados ou abaixo dos pisos, pode falhar. Confira
primeiro a saída de `check-coverage.mjs`; não reduza o baseline para contornar
uma regressão. A pasta `scripts` fica na **raiz do repositório**, não dentro de
`frontend`.

**Opcional — build de produção:** não é um teste, mas verifica a compilação do
frontend.

```powershell
Set-Location "$repo\frontend"
npm run build
Set-Location $repo
```

`backend/requirements-test.txt` declara as dependências de testes; o lock não
substitui a declaração das dependências de produção.

### Limites de cobertura

`scripts/coverage-baseline.json` guarda pisos de **linhas e branches por módulo**,
incluindo templates Angular, além dos totais. `check-coverage.mjs` falha se um
módulo desaparecer do relatório, ficar abaixo do piso ou surgir sem baseline
revisado. A atualização explícita `--write-baseline` somente mantém/aumenta os
pisos e preserva módulos ausentes; nunca deve ser usada para esconder uma
regressão. O total da aplicação Python também é verificado separadamente do
avaliador, para que testes do avaliador não escondam queda no backend.

A meta agregada mínima é **90% de linhas e 80% de branches** para backend,
aplicação backend e frontend. Esses valores são verificados independentemente
dos pisos revisados por módulo, que podem ser mais altos; a CI falha se qualquer
um dos limites ou pisos não for atingido.

Medição local após as integrações e os testes adicionais:

| Escopo | Linhas | Branches |
|---|---:|---:|
| Backend da aplicação | 92,81% | 86,21% |
| Python: aplicação + avaliador | 93,07% | 86,41% |
| Frontend Angular + templates | 90,69% | 81,54% |

Esses valores não significam cobertura de todos os cenários nem precisão clínica.
O relatório HTML Angular fica em `frontend/coverage/frontend/index.html`; o
backend produz JSON/XML. O AudioWorklet tem testes diretos do JavaScript real,
incluindo média de canais, lotes de 3 s, transferência e flush idempotente.
Seu resultado é separado da cobertura Angular. Após o complemento, passaram
350 testes backend, 115 testes Angular, 4 testes AudioWorklet e 6 cenários E2E.
Os E2E cobrem os fluxos descritos adiante, mas não exercitam diretamente a nova
ingestão contínua HTTP/FHIR nem a comparação acústica com referência; estas têm
testes unitários/componentes focados. Consulte as seções de validação para os
limites de cada suíte.

### Cenários adversos, concorrência e execução prolongada

Há testes para permissões negadas, desconexão de microfone, falha de processador
e fila de áudio excessiva, além de formato/tamanho/duração de payloads, timestamps
inválidos, sobreposição, retries e callbacks tardios. Requisições de áudio e
confirmação são exercitadas enquanto inferência visual está bloqueada, garantindo
que evidências e confirmações não sejam perdidas.

O teste de concorrência usa quatro escritores e 48 transações na mesma sessão:
alertas e registros de ida não duplicam. O orçamento local é P95 abaixo de 5 s
e máximo abaixo de 10 s por transação. Outro teste repete 250 consultas/sincronizações,
verifica histórico sem crescimento e pico de alocações Python abaixo de 8 MiB.
Esses orçamentos se aplicam aos testes de persistência, **não** ao YOLO, à nuvem
ou à capacidade hospitalar. Conexões SQLite usadas como context manager agora
fecham ao sair, tanto após commit como após rollback.

### Avaliador offline

O avaliador compara anotações de referência com predições exportadas em JSON.
Não lê mídia, não executa YOLO/Speech e não envia dados à nuvem:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m evaluation demo --output evaluation-report.json
.\.venv\Scripts\python.exe -m evaluation evaluate --references evaluation\examples\references.json --predictions evaluation\examples\predictions.json --tolerance-seconds 0.5 --output evaluation-report.json
Pop-Location
```

Ambos os arquivos contêm `dataset_kind`, `dataset_label` e `cases` com `case_id`
único. Cada caso contém `events` (`kind`, `timestamp_s` não negativo); predições
podem informar `latency_ms`. `transcript` e `angle_degrees` são opcionais, mas
precisam ser fornecidos nos dois lados. Identidades/casos devem coincidir;
dados inválidos, ausentes, duplicados ou não finitos são rejeitados.

Métricas: eventos pareados um a um dentro da tolerância inclusiva, TP/FP/FN,
precisão/recall/F1, WER de transcrição, MAE angular opcional e resumo de latência
quando informado. Métricas sem denominador/evidência são indisponíveis, não
"perfeitas". O demo é deliberadamente imperfeito: TP=2, FP=1, FN=1,
precisão/recall/F1 de aproximadamente 0,667; WER=0,4; MAE=2,5°.

**Avaliação real pendente:** coletar mídia autorizada/desidentificada, produzir
rótulos independentes, exportar predições do modelo real e executar o avaliador.
Os exemplos sintéticos validam o cálculo das métricas, não os modelos ou uma
decisão clínica. Métricas por casos reais devem incluir ruído, oclusão, iluminação,
posturas e diferentes formas de pedir ajuda; não reutilizar esse conjunto
como treinamento ou calibração do próprio teste.

### Integração contínua

`.github/workflows/quality.yml` executa em Windows/Python 3.14: testes e cobertura,
pisos por módulo, testes do próprio gate, AudioWorklet, build, E2E com navegador
e backend isolados e demo offline. Relatórios são publicados como artifacts,
inclusive em falhas. O workflow não precisa de secrets Azure. A execução remota
somente acontecerá após publicar estas alterações no GitHub.

Os seis cenários E2E usam Chromium e percorrem as interfaces reais: upload e
replay de leito com evidências sintéticas de imagem e fala, confirmação e
histórico/auditoria; upload de fisioterapia e relatório; consentimento e análise
de consulta de voz; monitoramento de câmera e microfone falsos com a implementação
real do AudioWorklet; importação dos exemplos sintéticos de sinais vitais,
prescrições e texto clínico. Os arquivos de teste são gerados localmente pelo FFmpeg,
e o servidor backend E2E substitui YOLO/Speech e bloqueia conexões externas.
O cenário de câmera também exercita o simulador vinculado à sessão e o
receptor HTTP sintético local.
Isso valida a integração e persistência da aplicação, não a precisão dos modelos
nem um cenário clínico real.

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
início e fim em segundos para cada intervalo, em ordem e sem sobreposição. Selecione
explicitamente a postura de cada intervalo; tempos decimais aceitam vírgula ou ponto
(por exemplo, `3,5` ou `3.5`). O início
é inclusivo e o fim exclusivo; deixe transições sem marcação quando a postura não
for clara. Lacunas são inconclusivas e não geram alertas de postura. Se o navegador
não reproduzir o formato original, os tempos ainda podem ser digitados; o servidor
confere os intervalos contra a duração do vídeo convertido. Para corrigir as
marcações de uma análise já enviada, reenvie o vídeo. Confira o resumo antes do
envio e a configuração salva no painel de métricas; para vídeos híbridos, os
intervalos informados ficam visíveis junto à postura atual.
Na postura deitada, um filtro experimental exige confiança mínima no ponto do rosto
e compara o comprimento projetado do tronco e a variação da direção da cabeça
com a referência inicial. Uma divergência acima de 10° entre as variações é
considerada inconclusiva; esse limite é uma heurística não validada. Frames que
falham nessas verificações não geram alerta de elevação e são registrados por
instante e motivo no campo `lying_trunk_inconclusive_frames` do relatório JSON.
O filtro pode aceitar pontos incorretos ou rejeitar movimentos reais; ausência
de alerta não confirma execução correta e requer validação profissional.
Nos vídeos com postura informada, os pontos do quadril, joelho e tornozelo são
suavizados por média exponencial (peso 0,4); uma perna só é medida quando seus
três pontos têm confiança mínima 0,5. A perda de confiança reinicia a suavização
da perna. Na postura deitada, o joelho também fica inconclusivo quando a
verificação conservadora do tronco falha, mesmo que seus pontos tenham confiança
suficiente; isso pode excluir medições válidas. Deitado, cada perna usa como referência seu primeiro ângulo confiável
em cada intervalo, e o limite de aumento de flexão é 30° por padrão, separado
do limite absoluto usado em pé ou sentado. As regras de postura exigem cinco
quadros consecutivos válidos na mesma perna; lacunas, oclusão e mudanças de
postura interrompem a contagem. O relatório lista quadros sem nenhuma medição
confiável de joelho em `knee_inconclusive_frames`; uma perna só é inicializada
quando seus pontos aparecem, mesmo que o exercício já esteja em andamento.
A suavização e confirmação podem atrasar ou perder movimentos breves.
Análises antigas sem postura informada mantêm a regra anterior.

Na aba **Leito com câmera**, abra a câmera do computador mediante permissão do
navegador. A prévia permanece local até iniciar: delimite manualmente a cerca
e salve suas posições no servidor. O monitoramento é bloqueado sem cerca salva.
Ao iniciar, imagens amostradas são analisadas por YOLO no backend local e o
microfone é enviado em trechos PCM ao Azure Speech. Saída da cerca e falas
críticas geram alertas independentes, persistidos com histórico de atendimento.
A opção de gravação permite salvar imagem e áudio no servidor ao encerrar;
desativada, não armazena vídeo, apenas cerca e histórico. O enquadramento deve
ser revisado ao mudar de câmera ou leito. Captura e inferência têm latência e
podem perder movimentos entre amostras; não é um sistema clínico validado.

Na telemetria, a visão é sempre combinada: escolha a aba **Vídeos gravados**
ou **Leito com câmera**. A coluna esquerda mostra upload e biblioteca de
gravações ou os leitos monitorados, respectivamente. Os dados clínicos e exames
são fictícios, locais e independentes do vídeo. Em telas largas, a descrição
fica acima do controle da cerca e do cenário; estes acompanham exatamente
as colunas do vídeo e dos sinais vitais.
Em telas menores, os blocos são empilhados. Na visão combinada, alertas clínicos
aparecem dentro do painel de monitoramento, em uma lista rolável por teclado;
em telas largas, a área de vídeo termina alinhada ao fim dos gráficos e os
alertas preenchem o espaço restante abaixo, com rolagem sem aumentar o painel;
Em telas largas, os cartões de fonte, vídeo e sinais têm a mesma altura. Esses
cartões não recebem sensores ou prontuário; uma consulta FHIR manual e autorizada
fica em uma seção separada e depende de configuração externa. Selecione um
cenário e inicie a simulação: as amostras avançam a cada 5 segundos; nos cenários
de alteração, os desvios ocorrem na segunda atualização. O cenário **Instável com
piora repentina** gera alertas aos 30 segundos simulados e para automaticamente
aos 40 segundos; reinicie para executá-lo novamente. O tempo exibido é baseado
nas amostras e pode atrasar em abas suspensas pelo navegador. A tabela e os gráficos de tendência mostram
as últimas oito amostras com escalas fixas; as linhas ligam os valores
simulados e não representam ECG nem formas de onda de monitores reais;
na tabela, uma área fixa para aproximadamente cinco linhas permite rolar as
demais amostras, mantendo o cabeçalho visível. A coluna data e hora registra
o horário local de geração, separado do tempo simulado da amostra;
pausar conserva a sequência e reiniciar ou trocar o cenário apaga os eventos
simulados. Os alertas de sinais e prescrição são gerados por regras fixas de
demonstração, sem persistência ou envio externo. Exames são exemplos estáticos
sem interpretação. Limites e alertas não são validados nem diagnósticos.
O histórico unificado reúne incidentes de imagem/fala de replay e câmera;
não inclui sinais vitais ou prescrições simuladas. Um webhook opcional pode
enviar alertas críticos confirmados de imagem/fala, mas não comprova contato com
equipe médica nem atendimento. Trocar de aba encerra a
sessão de vídeo e a câmera anterior, sem interromper a simulação clínica.
Ao navegar entre módulos, a sessão anterior é
encerrada.

### Simulador vinculado à sessão de mídia

Além dos cartões fictícios independentes acima, há um **segundo simulador**
associado explicitamente à sessão de câmera ou reprodução. Inicie o
monitoramento e selecione **Iniciar simulador de sinais e prescrição**. O
navegador solicita uma amostra sintética a cada 5 segundos enquanto o relógio
da sessão avança: a primeira é estável e as seguintes demonstram alteração
pré-programada de frequência cardíaca, oxigenação e dose. Os valores são
gerados no backend, não por sensores ou por análise do vídeo. Uma nota
igualmente sintética é analisada com as regras locais de menções; ela não
representa uma nota real importada nem usa o Azure.

As regras existentes de sinais vitais e comparação de prescrições geram
eventos para revisão. A tela lista evidências de imagem e fala da **mesma
sessão** cujos tempos estejam a até 10 s da amostra; isso não comprova
identidade do paciente ou relação causal. Os eventos e amostras são salvos
separadamente no SQLite e limitados a 1.000 amostras por sessão; a consulta
retorna as 100 mais recentes. O relógio sintético aceita até 30 minutos por
sessão. Pausar a reprodução ou suspender o navegador impede o avanço contínuo.

Quando há evento, o backend envia um aviso genérico ao receptor HTTP sintético
do próprio processo, em loopback. A entrega e eventuais falhas aparecem na
interface, com repetição manual idempotente; uma entrega interrompida pelo
reinício fica marcada como falha para nova tentativa. Esse receptor e sua fila
são independentes do webhook externo configurável e **não notificam uma equipe**.
O endpoint `POST /api/synthetic-stream/{session_id}/samples` aceita um UUID
`sample_id`, `timestamp` em segundos da sessão e `scenario` (`stable` ou
`change`); ele próprio gera os valores fictícios. Não envie dados de pacientes
nem trate essa API como integração com sensores ou prontuário.

1. `POST /api/videos` recebe multipart `file` e `mode` (`bed` ou `fisio`),
   limita o tamanho a 500 MB e retorna HTTP 202 com o identificador da análise.
   Para `fisio`, exige também `posture`, uma string JSON, por exemplo
   `{"type":"lying","intervals":[]}` ou
   `{"type":"hybrid","intervals":[{"start":0,"end":2.5,"posture":"standing"},{"start":3,"end":6,"posture":"lying"}]}`.
   As posturas aceitas são `standing`, `sitting` e `lying`; no híbrido, os
   intervalos são sequenciais, não sobrepostos, e medidos em segundos na linha
   do tempo do vídeo. Erros de duração são informados no estado de processamento.
2. Um worker serial em segundo plano converte MP4/AVI/MOV/WebM em H.264/AAC
   com FFmpeg, normalizando a linha do tempo para 25 fps. Usa somente a primeira
   faixa de áudio, quando presente, evitando decodificar faixas auxiliares como
   Apple APAC em MOVs que também possuem AAC. Vídeos sem áudio continuam aceitos.
   Falhas de conversão mostram erro específico de FFmpeg na interface e o
   diagnóstico detalhado no log do servidor. No modo **leito**,
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

#### Incidentes de imagem e fala

Replay e câmera compartilham uma correlação temporal por regras, com janela
de **10 segundos**, inclusive, nos timestamps da mesma sessão. Cada saída
da cerca virtual pode incorporar falas críticas detectadas nesse intervalo
(por exemplo, "socorro"). Havendo mais de uma saída próxima, a fala pertence
à saída mais próxima; empates usam a saída mais antiga. Falas do mesmo
timestamp ficam juntas. Avisos de severidade `warning` não entram nessa
correlação. Outras regras visuais não são associadas automaticamente à fala.
Não há reconhecimento de identidade do falante: uma fala próxima no tempo
pode não pertencer à pessoa acompanhada. Não é inferência de queda,
causalidade ou diagnóstico, nem um modelo de fusão treinado.

O painel **Incidentes · imagem e fala** mostra um incidente com as evidências:
origem, regra, tempo e transcrição final disponível. No replay, **Revisar em**
navega ao instante correspondente; retroceder encerra a passagem atual e cria
outra sessão ao reproduzir. A evidência visual persistida é o registro da
regra e do timestamp, não uma fotografia. Sem salvar a gravação da câmera,
não será possível rever seus pixels ou ouvir seu áudio posteriormente.

O primeiro alerta continua imediato, sem esperar a segunda modalidade.
Quando a outra evidência chega atrasada, atualiza o incidente existente.
Se incidentes antes separados forem unidos por uma saída detectada depois,
preserva-se o identificador mais antigo disponível; as incorporações ficam na
auditoria, sem duplicação no histórico unificado. Evidências provisórias são
identificadas e podem ser retiradas; sua versão anterior permanece auditável.
Retirar uma fala não retira um alerta visual confirmado. Uma nova evidência
não herda a confirmação de **Ir ao atendimento** de evidências anteriores.
O bip e o registro de atendimento continuam baseados nos alertas individuais,
preservados para rastreabilidade; o botão não comprova atendimento realizado.

**Consultar / atualizar histórico unificado** reúne câmera e gravações,
inclusive sessões encerradas e após reinício, com paginação e auditoria das
versões/evidências. Atualize manualmente para novas alterações. Os registros
ficam no SQLite local, incluindo transcrições associadas, sem novo envio à
nuvem por esta funcionalidade. Sessões antigas com alertas persistidos são
incorporadas ao iniciar o backend; não se inventam evidências inexistentes.
O relatório JSON da sessão de replay também contém os incidentes.

Para demonstrar sem câmera ou sensores: reproduza um vídeo de leito com
saída da cerca e fala crítica a até 10 s; observe primeiro a evidência
individual e depois a correlação, registre a ida e consulte o histórico.
Compare com fala fora da janela ou sem saída: o alerta individual permanece,
mas não aparece como multimodal. Vídeos sintéticos devem ser identificados
como tais e não constituem validação clínica.

O fluxo da demonstração é **carregar → reproduzir → analisar → alertar**.
Selecionar um vídeo pronto não carrega suas detecções ou transcrições antigas.
Somente **Reproduzir** inicia uma sessão, a partir da posição atual, sem confirmação
adicional para Azure. A prévia da câmera não envia áudio; ao iniciar explicitamente
o monitoramento de câmera, o microfone também usa Azure Speech.

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
vale na próxima reprodução, sem antecipar resultados. O webhook opcional não
garante notificação de uma equipe ou atendimento; este fluxo não captura microfone ao vivo.
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
e o botão não aciona equipe externa por si só. Um alerta confirmado pode já ter
sido enviado pelo webhook opcional. A intenção registrada em um aviso provisório continua
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
em relação à vertical > 35° gera aviso por padrão. Na posição deitada, a elevação
é a redução desse ângulo em relação ao primeiro frame confiável da pessoa
acompanhada em cada intervalo deitado. Elevação > 15° gera aviso por padrão;
o limite é ajustável separadamente. Comece cada intervalo com o tronco apoiado
e mantenha a câmera fixa. A referência não é reconhecimento automático de postura
correta: perspectiva, rotação e erros de keypoints podem afetar o resultado.
Sem alvo ou tronco confiável, não há medida nem alerta de elevação naquele frame.
Alterar a cerca recalcula a referência; alterar os limites recalcula os avisos.
Análises salvas são atualizadas ao reiniciar o backend, sem reenviar o vídeo.
A medida não avalia hiperextensão lombar. Em qualquer postura informada,
ângulo interno de flexão do joelho < 60°
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
é detecção comprovada de queda. Não há diagnóstico ou identificação do paciente;
o webhook opcional não comprova comunicação com uma equipe. O acompanhamento por caixa
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
A comparação acústica experimental também apresenta a taxa de cruzamentos por
zero no início e no fim de gravações de pelo menos 30 s, quando há janelas de
energia suficiente. Com saturação ou dados insuficientes, informa que a medida
está indisponível. O cálculo não separa voz de ruído e não identifica fadiga,
disartria ou dificuldade respiratória. Para comparar gravações, selecione uma
consulta processada e escolha manualmente outra gravação como referência.
Pitch mediano, amplitude de pitch, energia e cruzamentos por zero são calculados
somente em trechos reconhecidos como fala e comparados com limiares exploratórios.
O sistema não verifica se é a mesma pessoa, não controla o conteúdo ou a captação
e não classifica fadiga/disartria; diferenças são apenas sinalizações para revisão.
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

Nesta revisão, foram feitas chamadas reais controladas a Azure Speech e Azure
AI Language com frase e áudio sintéticos em português, sem dados pessoais.
Speech retornou a frase de teste; Language respondeu à análise textual. Essa
verificação pontual confirma conectividade naquele momento, não disponibilidade
futura, qualidade clínica, custos ou implantação da aplicação no Azure. As
suítes automatizadas continuam isoladas e usam provedores simulados.

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

Na consulta de voz, a aplicação também apresenta palavras por minuto estimadas,
duração reconhecida e pausas entre segmentos maiores que 0,5 s. São descritores
calculados sobre texto e tempos fornecidos pelo Azure Speech, não medidas
acústicas independentes. Erros de transcrição ou segmentação alteram os valores;
eles não estimam fadiga, disartria, respiração nem estado clínico.

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

## Importação de dados clínicos para revisão

Em `/telemetry`, o painel **Séries, prescrições e texto clínico** recebe arquivos
CSV/JSON manualmente. Os exemplos versionados estão em
[`backend/evaluation/examples/`](backend/evaluation/examples/): uma série de
96 pontos sintéticos ao longo de 24 horas, cinco versões de prescrição e uma
nota clínica sintética. Use os links do painel para baixá-los e demonstrar o
fluxo sem dados reais.

**Sinais vitais**: `POST /api/clinical-data/vitals` aceita CSV/JSON de até 5 MB
e 10.000 registros por arquivo. Campos obrigatórios: `recorded_at` (ISO 8601
com fuso), `patient_id` (pseudônimo), `heart_rate_bpm`, `systolic_mmhg`,
`diastolic_mmhg` e `spo2_percent`. Valores fora dos limites de entrada, pontos
duplicados para o mesmo pseudônimo/instante, pressão sistólica não superior à
diastólica e números não finitos são rejeitados. A análise cria eventos de
revisão para cruzamentos dos limites genéricos FC 50–120 bpm, sistólica
90–180 mmHg, diastólica 60–120 mmHg e SpO₂ 90–100%, além de variações absolutas
em até 30 minutos (FC/sistólica ≥30, diastólica ≥20 ou queda de SpO₂ ≥4 pontos).
Limites são regras fixas demonstrativas, não personalizadas por idade, condição
ou linha de base; não constituem limiares clínicos.

**Histórico de prescrições**: `POST /api/clinical-data/prescriptions` aceita
os mesmos formatos e limites. Registros contêm `patient_id`, `recorded_at`,
`medication`, `dose`, `unit`, `status` (`active` ou `discontinued`) e, se
disponíveis, `route` e `frequency`. Compara versões do mesmo medicamento dentro
do arquivo e mostra início, mudança, interrupção ou retomada para revisão.
Não valida indicação, interação, dose segura, ordem médica ou adesão.

**Nota clínica**: `POST /api/clinical-data/notes` aceita JSON de até 1 MB, com
`patient_id`, `recorded_at` e `text` de até 12.000 caracteres. É uma operação
separada, habilitada somente com `consent_to_cloud=true` e configuração de
Azure AI Language; só o texto da nota é enviado ao serviço. Azure Language
retorna termos-chave e sentimento do texto, e regras locais geram menções para
revisão. O texto original não é gravado localmente; o histórico guarda somente
metadados, métricas e termos derivados. A autorização na interface é uma
barreira técnica e não substitui consentimentos, base legal ou aprovação
institucional. Desidentifique o conteúdo antes do envio; o endpoint não detecta
nem remove automaticamente nomes, datas ou identificadores dentro da nota. Se
a análise falhar, o texto não é persistido.

`GET /api/clinical-data/imports` lista até 200 importações e seus resultados;
`GET /api/clinical-data/examples/{vitals|prescriptions|note}` baixa um exemplo.
Resultados ficam no SQLite local (`clinical_imports`) e são exibidos na linha
do tempo de revisão junto às evidências de vídeo/áudio, mas não são correlacionados
com esses incidentes nem acionam o webhook. Para entrada contínua, configure
`CLINICAL_INGEST_BEARER_TOKEN` no backend e use os endpoints da seção
[Ingestão contínua HTTP/FHIR](#ingestão-contínua-httpfhir). Eles associam
amostras a uma sessão ativa de câmera/reprodução e permitem regras de revisão e
webhook configurável. Sensores/prontuários não estão conectados por padrão;
uma consulta FHIR R4 manual também está disponível.
Pseudônimos são únicos dentro de cada
importação e não permitem vincular automaticamente a mesma pessoa entre arquivos.
O histórico guarda valores vitais e campos de prescrição enviados; use apenas
dados sintéticos ou autorizados e pseudonimizados. O nome de cada arquivo também
fica no histórico, portanto use nomes sem identificadores pessoais. Proteja o
banco local e estabeleça política de retenção antes de qualquer uso real.

Essas importações complementam a demonstração com entradas estruturadas, mas
não tornam o protótipo um sistema clínico integrado ou validado. A série e as
prescrições sintéticas testam a aplicação e suas regras, não a relevância dos
limites. Notas clínicas só devem ser enviadas após autorização apropriada e
avaliação da configuração e retenção do Azure.

### Consulta FHIR R4 opcional

Configure `FHIR_BASE_URL` e `FHIR_BEARER_TOKEN` no backend e reinicie-o. Em
**Consulta autorizada a prontuário FHIR R4**, informe o identificador, escolha
sinais vitais ou ordens de prescrição e confirme a autorização. A operação
`POST /api/clinical-data/fhir` consulta `Observation` ou `MedicationRequest`
somente para leitura. O identificador é enviado ao servidor configurado, mas não
é gravado no histórico local nem incluído nos logs HTTP do cliente.

São aceitos FC LOINC `8867-4` (`/min`), pressão sistólica `8480-6` e
diastólica `8462-4` (`mm[Hg]`) e oximetria de pulso `59408-5` (`%`), com
sistema UCUM explícito. Observações não reconhecidas, de outro sujeito ou com
estado incompatível são ignoradas com aviso; unidade inesperada, valores
ambíguos ou dados inválidos geram erro. Medições ausentes aparecem como
**indisponíveis**, sem imputação. Preservam-se até seis casas decimais de
segundo; precisão maior é rejeitada em vez de truncada.

Ordens `MedicationRequest` são apresentadas para revisão; não representam
histórico de versões, administração ou conferência de dose, interações ou
segurança. Doses ausentes ou complexas ficam indisponíveis e geram aviso.
O conector exige HTTPS, exceto HTTP de loopback para testes, não segue
redirecionamentos e restringe paginação à origem e ao caminho configurados;
limita cada página a 5 MB, 30 páginas e 10.000 recursos.

O fluxo foi exercitado com um servidor FHIR **sintético local**, não com um
prontuário real. Um servidor institucional pode exigir escopos, formatos ou
perfis adicionais; sua compatibilidade e autorização ainda precisam ser
verificadas. Valores e campos importados permanecem no SQLite, mesmo sem o
identificador original, e podem ser sensíveis.

### Ingestão contínua HTTP/FHIR

Configure `CLINICAL_INGEST_BEARER_TOKEN` no backend com um segredo aleatório
de ao menos 32 caracteres e reinicie o processo. Não reutilize o token FHIR ou
do webhook. O produtor envia amostras à sessão ativa pela API:

```http
POST /api/clinical-stream/{session_id}/samples
Authorization: Bearer <CLINICAL_INGEST_BEARER_TOKEN>
Content-Type: application/json

{
  "sample_id": "7f2ce844-7585-46fb-9517-3df7633df465",
  "source_id": "pseudônimo estável da fonte",
  "recorded_at": "2026-11-22T10:00:00Z",
  "elapsed_seconds": 12.5,
  "vitals": {"heart_rate_bpm": 132, "spo2_percent": 88},
  "prescriptions": [
    {"medication": "med-01", "dose": 10, "unit": "mg", "status": "active"}
  ]
}
```

`recorded_at` deve conter fuso horário; valores fora dos limites de entrada,
amostras fora de ordem, sessões encerradas e reuso do mesmo UUID com conteúdo
diferente são rejeitados. FC/pressão/SpO₂ usam as regras demonstrativas já
documentadas; mudanças de prescrição são comparadas com a amostra anterior.
Sinais precisam ser enviados como amostras consolidadas por fonte e instante.
O endpoint requer bearer token; **publique-o somente atrás de HTTPS e de uma
camada de autenticação/autorização da instituição**. Esta aplicação ainda é
local/monousuário, sem autenticação geral de usuários.

Um servidor FHIR R4 autorizado pode enviar `Bundle` `collection` ou `history`
para `POST /api/clinical-stream/{session_id}/fhir-subscription?source_id=case-01`
com o mesmo header de autorização. O `source_id` deve ser pseudônimo e os
`subject.reference` dos recursos devem apontar para `Patient/{source_id}`.
Observações aceitas usam os códigos LOINC/UCUM já descritos na seção FHIR;
ordens precisam de dose simples e unidade reconhecidas para comparação.
Recursos não compatíveis geram avisos ou erro explícito. O endpoint recebe
notificações, mas **não cria uma assinatura FHIR nem configura o servidor
remoto automaticamente**; essa configuração e a autorização cabem ao operador.

`GET /api/clinical-stream/{session_id}` retorna as 100 amostras mais recentes,
eventos de revisão, status de entrega e evidências de mídia da mesma sessão em
até 10 s. O SQLite mantém no máximo 1.000 amostras por fonte/sessão. Não envia
identificador institucional, valores vitais, medicamento ou nota no webhook;
preserva somente um identificador aleatório da sessão, categoria, campo e
instante do evento. Proteja o banco local e configure retenção antes de usar
dados autorizados.
O `GET` não exige autenticação própria nesta versão; a aplicação é monousuária
e não deve ser exposta a redes não confiáveis nem receber dados reais antes de
existirem HTTPS e autorização institucional para leitura.

### Webhook opcional de alertas

Por padrão `ALERT_WEBHOOK_ENABLED=false`. Para habilitar, configure no backend
`ALERT_WEBHOOK_ENABLED=true`, `ALERT_WEBHOOK_URL` HTTPS e
`ALERT_WEBHOOK_BEARER_TOKEN`; HTTP é aceito apenas em loopback. A URL não pode
conter usuário, senha, query ou fragmento. Reinicie o processo; o destinatário
deve validar o token e aceitar o cabeçalho `Idempotency-Key`.

Apenas novos alertas **críticos confirmados** das sessões de vídeo de leito ou
câmera e eventos de revisão gerados pela ingestão autenticada HTTP/FHIR são
enfileirados automaticamente. Eventos clínicos usam payload genérico com
referência pseudônima da sessão, tipo, campo e instante; não incluem valores,
medicamento, identificador institucional, transcrição ou nota. Alertas
provisórios e simuladores não são enviados. A referência de sessão não
identifica automaticamente um paciente; o integrador precisa estabelecer
qualquer mapeamento autorizado do seu lado.

O worker envia fora da transação. HTTP 2xx significa **aceitação pelo destino**,
não leitura pela equipe nem atendimento. Falhas de rede, HTTP 408/429 e 5xx
têm até cinco tentativas, com atrasos de 1, 5, 30 e 120 segundos; demais
respostas falham sem repetição automática. A fila em `webhook_outbox` preserva
estado e erro; a interface e `GET /api/notifications/status` permitem consulta,
e `POST /api/notifications/{id}/retry` repete uma entrega falha após correção.
Pendências de um processo encerrado são retomadas ao reiniciar com o webhook
habilitado. Alertas criados antes da habilitação não são enfileirados
retroativamente.

A entrega é **pelo menos uma vez**: após interrupção ou timeout, o destinatário
pode receber duplicatas e deve deduplicar pela chave. A retirada de confirmação
cancela entregas ainda pendentes, mas não desfaz um envio já iniciado. Perda de
energia, rede, serviço, autenticação ou acompanhamento humano pode impedir o
fluxo; não use este mecanismo para emergências ou como garantia de atendimento.
O teste ponta a ponta usa apenas um destinatário local sintético; não há ainda
evidência de integração com uma equipe ou serviço externo real.

## Verificação

Para executar as suítes de backend e frontend, consulte
[Como executar os testes no Windows](#como-executar-os-testes-no-windows).

Os testes de pipeline usam um modelo substituto explícito, mas conversão,
decodificação, Range HTTP e SQLite reais. A qualidade das predições deve ser
avaliada separadamente com os pesos e vídeos clínicos autorizados.