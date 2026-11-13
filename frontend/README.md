# Frontend

## Vídeos de fisioterapia e telemetria

- `/video` abre **Análise de vídeos de fisioterapia**, sem seletor de modalidade.
  Upload e biblioteca são exclusivos de fisioterapia, preservando replay, pose,
  ajustes de cerca, limites geométricos, eventos e relatório.
- `/telemetry` reúne **monitoramento de leitos e alertas**, com prévia local de
  câmera, upload de gravações de leito, análise de movimento e áudio durante o
  replay, cerca virtual, bip, histórico e registro de intenção de atendimento.
  Os blocos de métricas de movimento e registro de eventos são exclusivos de
  `/video`; na telemetria, permanecem os controles, alertas clínicos e histórico
  de atendimento, sem esses dois blocos.
  A cerca virtual permanece visível nas gravações, mesmo pausadas, sem pessoas
  detectadas ou enquanto a análise acompanha o vídeo. O ajuste mostra uma prévia
  imediata; ao desativar a regra, o limite continua cinza como referência, sem
  reativar alertas. Na aba de câmera, a marcação manual e o salvamento da cerca
  no servidor são obrigatórios antes de iniciar a análise. Os limites respeitam a imagem, inclusive com barras
  de enquadramento.
  Em **Ajustar cerca virtual**, pause antes da saída e arraste diretamente sobre
  a imagem para delimitar o leito. A marcação compensa barras de enquadramento e
  funciona com mouse ou toque; os controles percentuais continuam acessíveis
  por teclado. Arrastar apenas prepara a cerca: é necessário salvar. Depois,
  reproduza desde um instante com a pessoa dentro do limite, antes da saída,
  para iniciar o acompanhamento dos quadris. Não há reconhecimento automático
  da cama nem inferência de queda; alertas de fala permanecem independentes.
  Durante a edição, a cerca fica roxa e identificada como **prévia não aplicada**:
  a reprodução e a criação de sessões de análise são bloqueadas até **Salvar e
  aplicar cerca** (junto ao vídeo) ou **Cancelar edição**. Depois de salvar, o
  limite laranja é a cerca persistida e usada pela análise; a biblioteca também
  é atualizada para preservar o ajuste ao reabrir a gravação.
  **Ir ao atendimento** registra a ação com data e hora no servidor e atualiza
  o histórico automaticamente. Após a confirmação, o bip para e o painel fica
  verde, indicando ida registrada; novos eventos críticos voltam a acionar o
  alerta. O painel verde desaparece após 5 segundos, sem apagar o histórico,
  e reaparece se houver outro evento crítico. Falha ao salvar mantém o alerta ativo. Esse registro não comprova
  presença no leito nem atendimento concluído.
  A navegação entre páginas encerra a câmera e a sessão anterior.
- As gravações usam o mesmo workspace de vídeo nas duas rotas, com modalidade
  fixa por página. A câmera possui captura ao vivo própria e reutiliza os
  serviços de pose, cerca e registro de alertas do backend.
- A telemetria usa somente a visão combinada, com abas internas **Vídeos
  gravados** e **Leito com câmera**. Gravações de leito e biblioteca ocupam a
  coluna esquerda na primeira aba; na segunda, ela mostra os leitos monitorados.
  Trocar de aba encerra o workspace anterior e libera câmera e sessão, sem
  interromper os dados fictícios. A câmera é aberta somente após a ação do usuário.
  Em telas largas, uma descrição única fica acima do controle da cerca e do
  cenário de dados; o controle tem a mesma largura e posição do vídeo, e o
  cenário acompanha a coluna dos sinais. Os cartões principais têm a mesma
  altura. O título “Paciente fictício · Leito 1” foi removido. Os alertas
  clínicos ficam dentro do painel de monitoramento, com lista rolável e acessível
  por teclado. Em telas largas, a área de vídeo termina na mesma linha dos
  gráficos, e o painel de alertas ocupa o espaço restante abaixo, sem crescer
  conforme a quantidade de eventos;
  Em telas menores, o
  vídeo e os sinais são empilhados, e
  prescrições e exames aparecem após os alertas.
- Na aba **Leito com câmera**, use **Abrir câmera**, delimite a cerca por arraste
  ou controles percentuais e **Salvar e aplicar cerca da câmera**. As posições
  persistem no servidor; revise ao mudar câmera, enquadramento ou leito.
  **Iniciar monitoramento com imagem e áudio** solicita o microfone e inicia
  YOLO no backend local e Speech no Azure. A prévia anterior ao início não
  envia imagem/áudio. A saída dos quadris da pessoa acompanhada gera evento
  de imagem, independente das falas. Use com a pessoa dentro da cerca ao iniciar.
  Não é um detector validado de queda, nem um monitor clínico.
  A captura de imagem é amostrada e serializada, com intervalo mínimo de 200 ms
  após a resposta; FPS e latência dependem da inferência. Movimentos entre
  amostras podem não ser detectados. Áudio é mono PCM 16 kHz em trechos de cerca
  de 3 segundos; falha explícita ou fila excessiva interrompe o monitoramento.
  A opção **Salvar gravação de imagem e áudio** é escolhida antes de iniciar;
  desativada, somente cerca e histórico são persistidos. **Parar monitoramento
  e finalizar** conclui envios pendentes e a gravação, quando habilitada.
  Alertas podem ser confirmados por **Ir ao atendimento**, com data/hora e
  histórico próprios da câmera, mesmo após parar; o painel verde some em 5 s.
- Dados clínicos são fictícios e locais, não vêm de sensores, banco de dados ou
  do vídeo. Escolha um cenário e inicie a simulação: uma amostra é adicionada a
  cada 5 segundos. Nos cenários de alteração de sinais ou prescrição, a mudança
  ocorre na segunda atualização. Em **Instável com piora repentina**, a piora
  ocorre aos 30 segundos simulados, gera alertas de sinais e a execução termina
  automaticamente aos 40 segundos; use reiniciar para executar novamente.
  O tempo é medido pelas amostras e pode atrasar em abas suspensas pelo navegador.
  Pausar conserva a sequência; reiniciar ou trocar de cenário a limpa. Há uma tabela
  das últimas oito amostras e gráficos de tendência com escalas fixas; as linhas
  unem somente as amostras e não representam ECG ou ondas reais de monitor.
  A tabela tem altura fixa para aproximadamente cinco linhas, cabeçalho fixo e
  rolagem acessível por teclado. Após a identificação e o tempo simulado da
  amostra, apresenta data e hora locais de sua geração; pausas não alteram
  horários já registrados e reiniciar gera uma nova amostra inicial.
  Também há prescrições fictícias e exames estáticos sem
  interpretação. Os alertas de sinais e prescrição são gerados por regras fixas
  demonstrativas, exibidos apenas na tela e não persistidos nem enviados.
- Os limites e a alteração de dose são exemplos, não critérios clínicos
  validados. Uma integração real exige identificação, histórico, dados confiáveis,
  validação clínica e um mecanismo apropriado de notificação.

Alertas de leito são experimentais e exibidos no painel; não notificam
externamente a equipe médica. A câmera tem prévia local antes do início e
análise de imagem e áudio somente após salvar a cerca e iniciar explicitamente.

## Módulo de voz

Áudio, transcrição e menções clínicas ficam lado a lado em telas largas. A biblioteca
fica recolhida quando há uma consulta selecionada e usa rolagem horizontal ao abrir,
enquanto transcrições e menções extensas têm rolagem interna
acessível por teclado. Sentimento, indicadores acústicos, instruções de importação
e limitações são expansíveis. Em telas menores, os painéis se empilham e a página
mantém a rolagem vertical, sem cortar conteúdo.

Menções críticas não negadas recebem destaque de alta prioridade na biblioteca e
no painel clínico, inclusive quando a análise de linguagem falha parcialmente.
Esse destaque solicita revisão humana; não é diagnóstico nem notificação externa.

This project was generated using [Angular CLI](https://github.com/angular/angular-cli) version 21.2.21.

## Development server

To start a local development server, run:

```bash
ng serve
```

Once the server is running, open your browser and navigate to `http://localhost:4200/`. The application will automatically reload whenever you modify any of the source files.

## Code scaffolding

Angular CLI includes powerful code scaffolding tools. To generate a new component, run:

```bash
ng generate component component-name
```

For a complete list of available schematics (such as `components`, `directives`, or `pipes`), run:

```bash
ng generate --help
```

## Building

To build the project run:

```bash
ng build
```

This will compile your project and store the build artifacts in the `dist/` directory. By default, the production build optimizes your application for performance and speed.

## Running unit tests

To execute unit tests with the [Vitest](https://vitest.dev/) test runner, use the following command:

```bash
ng test
```

## Running end-to-end tests

For end-to-end (e2e) testing, run:

```bash
ng e2e
```

Angular CLI does not come with an end-to-end testing framework by default. You can choose one that suits your needs.

## Additional Resources

For more information on using the Angular CLI, including detailed command references, visit the [Angular CLI Overview and Command Reference](https://angular.dev/tools/cli) page.
