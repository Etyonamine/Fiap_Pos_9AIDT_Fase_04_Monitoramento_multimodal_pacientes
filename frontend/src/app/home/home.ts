import { Component, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

type Tone = 'ok' | 'info' | 'warn' | 'danger';

interface Field { label: string; value: string; tone: Tone; }
interface Module {
  id: 'video' | 'voice' | 'telemetry';
  title: string;
  subtitle: string;
  fields: Field[];
  cta: string;
  route: string;
}
interface Incident { date: string; description: string; status: string; tone: Tone; }

@Component({
  selector: 'app-home',
  imports: [RouterLink],
  templateUrl: './home.html',
  styleUrl: './home.scss',
})
export class Home {
  protected readonly incidentsOpen = signal(true);

  protected readonly summary = [
    { label: 'Pacientes ativos', value: '14', tone: 'info' as Tone },
    { label: 'Vídeo', value: 'ARQUIVOS LOCAIS', tone: 'info' as Tone },
    { label: 'Alertas pendentes', value: '01', tone: 'warn' as Tone },
    { label: 'Voz', value: 'IMPORTAÇÃO / AZURE', tone: 'info' as Tone },
  ];

  protected readonly modules: Module[] = [
    {
      id: 'video',
      title: 'Análise de vídeos de fisioterapia',
      subtitle: 'Postura e movimentos durante os exercícios',
      fields: [
        { label: 'Origem', value: 'Upload de vídeo', tone: 'info' },
        { label: 'Análise', value: 'Exercícios de fisioterapia', tone: 'info' },
        { label: 'Replay', value: 'Sincronizado por timestamp', tone: 'ok' },
      ],
      cta: 'Analisar vídeo de fisioterapia',
      route: '/video',
    },
    {
      id: 'voice',
      title: 'Voz e transcrição',
      subtitle: 'Análise de fala e linguagem natural',
      fields: [
        { label: 'Origem', value: 'Upload de consulta e replay', tone: 'info' },
        { label: 'Transcrição', value: 'Azure Speech to Text', tone: 'info' },
        { label: 'Linguagem', value: 'Sentimento e termos-chave no Azure', tone: 'info' },
      ],
      cta: 'Abrir análise de áudio',
      route: '/voice',
    },
    {
      id: 'telemetry',
      title: 'Telemetria e anomalias',
      subtitle: 'Monitoramento de leitos e segurança do paciente',
      fields: [
        { label: 'Movimento', value: 'Gravações de leito e alertas', tone: 'info' },
        { label: 'Sinais vitais', value: 'Não integrado', tone: 'warn' },
        { label: 'Prescrições', value: 'Não integrado', tone: 'warn' },
      ],
      cta: 'Abrir telemetria e leitos',
      route: '/telemetry',
    },
  ];

  protected readonly incidents: Incident[] = [
    { date: '07/11 - 22:30', description: 'Paciente fora dos limites da cerca virtual', status: 'Médio', tone: 'warn' },
    { date: '07/11 - 12:20', description: 'Pico crítico detectado', status: 'Pico identificado', tone: 'danger' },
    { date: '17/11 - 19:30', description: 'Sessão ativa', status: 'Baixo', tone: 'ok' },
  ];

  protected readonly waveBars = [8,14,22,34,50,70,90,100,80,60,85,95,70,50,65,80,55,40,30,45,35,25,18,12,8,5];

  protected toggleIncidents(): void {
    this.incidentsOpen.update((v) => !v);
  }

}
