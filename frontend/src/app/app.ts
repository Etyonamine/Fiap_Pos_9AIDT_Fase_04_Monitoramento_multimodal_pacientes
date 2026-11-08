import { DatePipe } from '@angular/common';
import { Component, inject, OnDestroy, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { WebSocketConnection } from './websocket-connection';

@Component({
  selector: 'app-root',
  imports: [DatePipe, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnDestroy {
  protected readonly websocket = inject(WebSocketConnection);
  protected readonly now = signal(new Date());
  private readonly timer = setInterval(() => this.now.set(new Date()), 30_000);

  ngOnDestroy(): void {
    clearInterval(this.timer);
  }
}
