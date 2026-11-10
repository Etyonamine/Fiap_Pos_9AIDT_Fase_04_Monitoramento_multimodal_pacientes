import { Routes } from '@angular/router';
import { Home } from './home/home';
import { Voice } from './voice/voice';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    component: Home,
    title: 'YtosMedialAI · Análise clínica multimodal',
  },
  {
    path: 'video',
    loadComponent: () => import('./video/video').then((module) => module.Video),
    title: 'YtosMedialAI · Análise de vídeos de fisioterapia',
  },
  { path: 'voice', component: Voice, title: 'YtosMedialAI · Voz e transcrição' },
  {
    path: 'telemetry',
    loadComponent: () => import('./telemetry/telemetry').then((module) => module.Telemetry),
    title: 'YtosMedialAI · Telemetria e anomalias',
  },
  { path: '**', redirectTo: '' },
];
