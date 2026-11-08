import { DOCUMENT } from '@angular/common';
import { inject, Injectable, OnDestroy, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class WebSocketConnection implements OnDestroy {
  private readonly connected = signal(false);
  readonly online = this.connected.asReadonly();
  private socket: WebSocket | null = null;
  private retry: ReturnType<typeof setTimeout> | undefined;
  private destroyed = false;
  private readonly location = inject(DOCUMENT).defaultView?.location;

  constructor() {
    this.connect();
  }

  private connect(): void {
    if (this.destroyed || !this.location || typeof WebSocket === 'undefined') return;

    try {
      const url = new URL('/api/ws', this.location.href);
      url.protocol = this.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const socket = new WebSocket(url.href);
      this.socket = socket;
      socket.onopen = () => this.connected.set(true);
      socket.onerror = () => this.connected.set(false);
      socket.onclose = () => {
        this.connected.set(false);
        this.socket = null;
        this.reconnect();
      };
    } catch {
      this.connected.set(false);
      this.reconnect();
    }
  }

  private reconnect(): void {
    if (!this.destroyed) this.retry = setTimeout(() => this.connect(), 5_000);
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    clearTimeout(this.retry);
    if (this.socket) {
      this.socket.onopen = null;
      this.socket.onerror = null;
      this.socket.onclose = null;
      this.socket.close();
      this.socket = null;
    }
    this.connected.set(false);
  }
}
