import { Routes } from '@angular/router';
import { Home } from './home/home';
import { Telemetry } from './telemetry/telemetry';
import { Video } from './video/video';
import { Voice } from './voice/voice';

export const routes: Routes = [
  { path: '', pathMatch: 'full', component: Home },
  { path: 'video', component: Video },
  { path: 'voice', component: Voice },
  { path: 'telemetry', component: Telemetry },
  { path: '**', redirectTo: '' },
];
