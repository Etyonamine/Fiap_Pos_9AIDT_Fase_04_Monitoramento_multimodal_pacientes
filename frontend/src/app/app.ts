import { DatePipe } from '@angular/common';
import { Component, computed, inject, OnDestroy, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';
import { WebSocketConnection } from './websocket-connection';

@Component({
  selector: 'app-root',
  imports: [DatePipe, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnDestroy {
  private readonly router = inject(Router);
  private readonly routeUrl = toSignal(
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );
  protected readonly pageTitle = computed(() => {
    const url = this.routeUrl().split(/[?#]/)[0];
    if (url === '/video') return 'Análise de vídeos de fisioterapia';
    if (url === '/telemetry') return 'Telemetria e anomalias';
    if (url === '/voice') return 'Voz e transcrição';
    return 'Análise clínica multimodal';
  });
  protected readonly websocket = inject(WebSocketConnection);
  protected readonly now = signal(new Date());
  private readonly timer = setInterval(() => this.now.set(new Date()), 30_000);

  ngOnDestroy(): void {
    clearInterval(this.timer);
  }
}
