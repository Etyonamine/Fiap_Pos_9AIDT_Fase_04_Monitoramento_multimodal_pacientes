import { registerLocaleData } from '@angular/common';
import localePt from '@angular/common/locales/pt';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { App } from './app';
import { WebSocketConnection } from './websocket-connection';

class TestSocket {
  static instances: TestSocket[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();

  constructor(readonly url: string) {
    TestSocket.instances.push(this);
  }
}

describe('App', () => {
  beforeEach(async () => {
    registerLocaleData(localePt, 'pt-BR');
    vi.useFakeTimers();
    TestSocket.instances = [];
    vi.stubGlobal('WebSocket', TestSocket);
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  afterEach(() => {
    TestBed.resetTestingModule();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('shows a disconnected alert until the actual WebSocket opens', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const pill: HTMLElement = fixture.nativeElement.querySelector('.status-pill');
    expect(pill.textContent).toContain('NÃO CONECTADO');
    expect(pill.classList.contains('disconnected')).toBe(true);
    expect(pill.getAttribute('role')).toBe('status');
    expect(pill.getAttribute('aria-live')).toBe('polite');
    const socket = TestSocket.instances[0];
    const url = new URL(socket.url);
    expect(url.protocol).toBe(window.location.protocol === 'https:' ? 'wss:' : 'ws:');
    expect(url.host).toBe(window.location.host);
    expect(url.pathname).toBe('/api/ws');

    socket.onopen?.();
    fixture.detectChanges();
    expect(pill.textContent).toContain('ATIVO');
    expect(pill.classList.contains('disconnected')).toBe(false);
  });

  it('returns to the red alert on errors and reconnects only after reopening', () => {
    const fixture = TestBed.createComponent(App);
    const socket = TestSocket.instances[0];
    socket.onopen?.();
    fixture.detectChanges();
    const pill: HTMLElement = fixture.nativeElement.querySelector('.status-pill');
    expect(pill.classList.contains('disconnected')).toBe(false);

    socket.onerror?.();
    fixture.detectChanges();
    expect(pill.textContent).toContain('NÃO CONECTADO');
    expect(pill.classList.contains('disconnected')).toBe(true);
    socket.onclose?.();
    vi.advanceTimersByTime(5_000);
    fixture.detectChanges();
    expect(TestSocket.instances).toHaveLength(2);
    expect(pill.textContent).toContain('NÃO CONECTADO');

    TestSocket.instances[1].onopen?.();
    fixture.detectChanges();
    expect(pill.textContent).toContain('ATIVO');
    expect(pill.classList.contains('disconnected')).toBe(false);
  });

  it('shows the alert when an open WebSocket closes without an error', () => {
    const fixture = TestBed.createComponent(App);
    TestSocket.instances[0].onopen?.();
    fixture.detectChanges();
    TestSocket.instances[0].onclose?.();
    fixture.detectChanges();
    const pill: HTMLElement = fixture.nativeElement.querySelector('.status-pill');
    expect(pill.textContent).toContain('NÃO CONECTADO');
    expect(pill.classList.contains('disconnected')).toBe(true);
  });

  it('stays disconnected and retries if socket construction fails', () => {
    vi.stubGlobal('WebSocket', vi.fn(function () {
      throw new Error('WebSocket unavailable');
    }));
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.status-pill').textContent).toContain('NÃO CONECTADO');
    vi.stubGlobal('WebSocket', TestSocket);
    vi.advanceTimersByTime(5_000);
    expect(TestSocket.instances).toHaveLength(1);
  });

  it('closes the socket and cancels retries when the application is destroyed', () => {
    TestBed.createComponent(App);
    const socket = TestSocket.instances[0];
    const connection = TestBed.inject(WebSocketConnection);
    socket.onopen?.();
    connection.ngOnDestroy();
    expect(socket.close).toHaveBeenCalledOnce();
    expect(socket.onopen).toBeNull();
    expect(connection.online()).toBe(false);
    vi.advanceTimersByTime(5_000);
    expect(TestSocket.instances).toHaveLength(1);
  });

  it('cancels a pending reconnect when the application is destroyed', () => {
    TestBed.createComponent(App);
    TestSocket.instances[0].onclose?.();
    TestBed.inject(WebSocketConnection).ngOnDestroy();
    vi.advanceTimersByTime(5_000);
    expect(TestSocket.instances).toHaveLength(1);
  });
});
