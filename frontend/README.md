# Frontend

## Vídeos de fisioterapia e telemetria

- `/video` abre **Análise de vídeos de fisioterapia**, sem seletor de modalidade.
  Upload e biblioteca são exclusivos de fisioterapia, preservando replay, pose,
  ajustes de cerca, limites geométricos, eventos e relatório.
- `/telemetry` reúne **monitoramento de leitos e alertas**, com prévia local de
  câmera, upload de gravações de leito, análise de movimento e áudio durante o
  replay, cerca virtual, bip, histórico e registro de intenção de atendimento.
  A navegação entre páginas encerra a câmera e a sessão anterior.
- As duas rotas usam o mesmo workspace de vídeo, com modalidade fixa por página;
  não duplicam rotinas de análise nem alteram a modalidade dos arquivos existentes.
- Sinais vitais (batimentos, pressão arterial e oxigenação) e evolução de
  prescrições possuem seções próprias na telemetria, mas **não estão integrados**.
  Não são exibidos valores, séries ou alertas clínicos fictícios. A ativação exige
  fontes de dados e critérios de detecção validados pela equipe clínica.

Alertas de leito são experimentais e exibidos no painel; não notificam
externamente a equipe médica. A câmera é somente uma prévia sem análise.

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
