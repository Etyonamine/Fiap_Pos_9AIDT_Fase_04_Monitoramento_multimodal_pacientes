import { Component, OnDestroy, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
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
  imports: [DatePipe, RouterLink],
  templateUrl: './home.html',
  styleUrl: './home.scss',
})
export class Home implements OnDestroy {
  protected readonly now = signal(new Date());
  private readonly timer = setInterval(() => this.now.set(new Date()), 30_000);

  protected readonly incidentsOpen = signal(true);

  protected readonly summary = [
    { label: 'Pacientes ativos', value: '14', tone: 'info' as Tone },
    { label: 'Câmeras', value: '02 LIGADAS', tone: 'ok' as Tone },
    { label: 'Alertas pendentes', value: '01', tone: 'warn' as Tone },
    { label: 'Serviços de voz', value: 'DISPONÍVEIS', tone: 'ok' as Tone },
  ];

  protected readonly modules: Module[] = [
    {
      id: 'video',
      title: 'Análise de vídeo e postura',
      subtitle: 'Visão computacional e inteligência artificial local',
      fields: [
        { label: 'Câmera', value: 'ATIVA', tone: 'ok' },
        { label: 'Rastreamento', value: '1 paciente', tone: 'info' },
        { label: 'Estado de segurança', value: 'Seguro', tone: 'ok' },
      ],
      cta: 'Abrir monitoramento por vídeo',
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

  ngOnDestroy(): void {
    clearInterval(this.timer);
  }
}
