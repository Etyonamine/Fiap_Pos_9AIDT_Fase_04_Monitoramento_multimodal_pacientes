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
    { label: 'Serviços de voz', value: 'DISPONÍVEIS', tone: 'ok' as Tone },
  ];

  protected readonly modules: Module[] = [
    {
      id: 'video',
      title: 'Análise de vídeo e postura',
      subtitle: 'Laboratório de análise forense com vídeos gravados',
      fields: [
        { label: 'Origem', value: 'Upload de vídeo', tone: 'info' },
        { label: 'Modos', value: 'Leito / Fisioterapia', tone: 'info' },
        { label: 'Replay', value: 'Sincronizado por timestamp', tone: 'ok' },
      ],
      cta: 'Abrir laboratório de vídeo',
      route: '/video',
    },
    {
      id: 'voice',
      title: 'Voz e transcrição',
      subtitle: 'Análise de fala e linguagem natural',
      fields: [
        { label: 'Sessão', value: 'PT-8842 — gravação', tone: 'info' },
        { label: 'Transcrição', value: 'Disponível (98%)', tone: 'ok' },
        { label: 'Status', value: 'Monitorando áudio', tone: 'ok' },
      ],
      cta: 'Abrir análise de áudio',
      route: '/voice',
    },
    {
      id: 'telemetry',
      title: 'Telemetria e anomalias',
      subtitle: 'Sinais vitais e padrões de segurança do paciente',
      fields: [
        { label: 'Sensores', value: '3 sinais vitais conectados', tone: 'info' },
        { label: 'Anomalia', value: 'Alerta ativado', tone: 'danger' },
        { label: 'Revisão', value: '1 pendente', tone: 'warn' },
      ],
      cta: 'Abrir sinais vitais e alertas',
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
