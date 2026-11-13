import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, computed, effect, inject, signal, viewChild } from '@angular/core';
import { firstValueFrom, timeout } from 'rxjs';
import { AlertLogEntry, CameraMonitorState, Fence, MonitorAlert, VideoApi, VideoEvent } from './video-api';

const INITIAL_FENCE: Fence = { enabled: true, x: .1, y: .1, width: .8, height: .8 };

export function cameraWav(samples: Float32Array, sampleRate: number): Blob {
  const outputRate = 16000;
  const length = Math.floor(samples.length * outputRate / sampleRate);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  text(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true);
  text(8, 'WAVE'); text(12, 'fmt '); view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, outputRate, true); view.setUint32(28, outputRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, 'data'); view.setUint32(40, length * 2, true);
  for (let i = 0; i < length; i++) {
    const start = Math.floor(i * sampleRate / outputRate);
    const end = Math.min(samples.length, Math.max(start + 1, Math.floor((i + 1) * sampleRate / outputRate)));
    let value = 0;
    for (let j = start; j < end; j++) value += samples[j];
    value = Math.max(-1, Math.min(1, value / (end - start)));
    view.setInt16(44 + i * 2, value * (value < 0 ? 32768 : 32767), true);
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

@Component({
  selector: 'app-camera-monitor',
  imports: [DatePipe],
  templateUrl: './camera-monitor.html',
  styleUrl: './camera-monitor.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CameraMonitor {
  readonly bones = [[5, 6], [5, 7], [7, 9], [6, 8], [8, 10], [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16]];
  private readonly api = inject(VideoApi);
  private readonly destroyRef = inject(DestroyRef);
  readonly player = viewChild<ElementRef<HTMLVideoElement>>('cameraPlayer');
  readonly active = signal(false);
  readonly starting = signal(false);
  readonly stopping = signal(false);
  readonly preview = signal(false);
  readonly editing = signal(false);
  readonly saving = signal(false);
  readonly fenceLoading = signal(true);
  readonly record = signal(false);
  readonly savedFence = signal<Fence | null>(null);
  readonly fence = signal<Fence>({ ...INITIAL_FENCE });
  readonly dimensions = signal({ width: 640, height: 480 });
  readonly state = signal<CameraMonitorState | null>(null);
  readonly alerts = signal<MonitorAlert[]>([]);
  readonly events = signal<VideoEvent[]>([]);
  readonly history = signal<AlertLogEntry[]>([]);
  readonly acknowledging = signal(false);
  readonly hidden = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly soundError = signal('');
  readonly elapsed = signal(0);
  readonly pending = computed(() => this.alerts().filter(a => !a.acknowledged_at && a.status !== 'retracted'));
  readonly attention = computed(() => this.pending().length > 0);
  readonly acknowledged = computed(() => this.alerts().filter(a => a.acknowledged_at));
  readonly hasAlerts = computed(() => this.alerts().some(a => a.status !== 'retracted'));
  readonly canStart = computed(() => this.preview() && !!this.savedFence() && !this.editing() &&
    !this.fenceLoading() && !this.saving() && !this.starting() && !this.stopping() && !this.active() &&
    (!this.state() || this.state()?.closed === true));
  private stream: MediaStream | null = null;
  private generation = 0;
  private destroyed = false;
  private frameTimer: ReturnType<typeof setTimeout> | null = null;
  private frameRequest: Promise<void> = Promise.resolve();
  private audioContext: AudioContext | null = null;
  private audioSource: MediaStreamAudioSourceNode | null = null;
  private audioNode: AudioWorkletNode | null = null;
  private audioQueue: Promise<void> = Promise.resolve();
  private queuedAudio = 0;
  private audioSamples = 0;
  private audioOffset = 0;
  private flushResolve: (() => void) | null = null;
  private startedAt = 0;
  private beepContext: AudioContext | null = null;
  private beepTimer: ReturnType<typeof setInterval> | null = null;
  private drag: { x: number; y: number; id: number; svg: SVGSVGElement; previous: Fence } | null = null;

  constructor() {
    void this.loadFence();
    effect(onCleanup => {
      const pending = this.attention();
      const hasAlerts = this.hasAlerts();
      this.hidden.set(false);
      if (pending) this.startBeep();
      else this.stopBeep();
      if (!pending && hasAlerts) {
        const timeout = setTimeout(() => this.hidden.set(true), 5000);
        onCleanup(() => clearTimeout(timeout));
      }
    });
    this.destroyRef.onDestroy(() => {
      this.destroyed = true;
      void this.disconnect();
      this.stopBeep();
      void this.beepContext?.close().catch(error => this.fail(error));
    });
  }

  private async loadFence() {
    try {
      const result = await firstValueFrom(this.api.cameraFence());
      if (this.destroyed) return;
      this.savedFence.set(result.fence);
      if (result.fence) this.fence.set({ ...result.fence });
    } catch (error) { this.fail(error); }
    finally { this.fenceLoading.set(false); }
  }

  async connect() {
    if (this.preview() || this.starting()) return;
    const generation = ++this.generation;
    this.starting.set(true);
    this.error.set('');
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Câmera indisponível. Use localhost ou HTTPS.');
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      if (generation !== this.generation || this.destroyed) {
        stream.getTracks().forEach(track => track.stop()); return;
      }
      this.stream = stream;
      stream.getVideoTracks().forEach(track => track.addEventListener('ended', () => {
        this.error.set('Câmera desconectada. Monitoramento interrompido.');
        void this.disconnect();
      }));
      const player = this.player()?.nativeElement;
      if (!player) throw new Error('Não foi possível abrir a imagem da câmera.');
      player.srcObject = stream;
      await player.play();
      if (generation !== this.generation || this.destroyed) return;
      this.preview.set(true);
      this.onLoaded();
      if (!this.savedFence()) this.editing.set(true);
      this.notice.set('Marque e salve a área do leito antes de iniciar. Microfone só será solicitado ao iniciar a análise.');
    } catch (error) {
      if (generation === this.generation) { await this.disconnect(); this.fail(error); }
    } finally { if (generation === this.generation) this.starting.set(false); }
  }

  onLoaded() {
    const player = this.player()?.nativeElement;
    if (!player?.videoWidth || !player.videoHeight) return;
    const old = this.dimensions();
    if (this.active() && (old.width !== player.videoWidth || old.height !== player.videoHeight)) {
      this.error.set('Enquadramento alterado. Monitoramento interrompido; revise e salve a cerca.');
      void this.stopMonitoring();
      this.savedFence.set(null);
      this.editing.set(true);
    }
    this.dimensions.set({ width: player.videoWidth, height: player.videoHeight });
  }

  editFence() {
    if (!this.preview() || this.fenceLoading() || this.active() || this.starting() || this.stopping()) return;
    this.fence.set({ ...(this.savedFence() ?? INITIAL_FENCE) });
    this.editing.set(true);
  }

  changeFence(key: 'x' | 'y' | 'width' | 'height', event: Event) {
    const value = Number((event.target as HTMLInputElement).value) / 100;
    this.fence.update(f => {
      const next = { ...f, [key]: value };
      next.width = Math.min(next.width, 1 - next.x);
      next.height = Math.min(next.height, 1 - next.y);
      return next;
    });
  }

  pointer(event: PointerEvent, action: 'start' | 'move' | 'end' | 'cancel') {
    if (!this.editing() || this.fenceLoading() || this.saving() || !(event.currentTarget instanceof SVGSVGElement)) return;
    const svg = event.currentTarget;
    const b = svg.getBoundingClientRect(), d = this.dimensions();
    const scale = Math.min(b.width / d.width, b.height / d.height);
    if (!scale) return;
    const x = (event.clientX - b.left - (b.width - d.width * scale) / 2) / (d.width * scale);
    const y = (event.clientY - b.top - (b.height - d.height * scale) / 2) / (d.height * scale);
    if (action === 'start') {
      if (event.button !== 0 || this.drag) return;
      if (x < 0 || x > 1 || y < 0 || y > 1) {
        this.notice.set('Marque sobre a imagem, não nas barras de enquadramento.'); return;
      }
      event.preventDefault(); svg.setPointerCapture(event.pointerId);
      this.drag = { x, y, id: event.pointerId, svg, previous: { ...this.fence() } };
      return;
    }
    const drag = this.drag;
    if (!drag || drag.id !== event.pointerId) return;
    const cx = Math.max(0, Math.min(1, x)), cy = Math.max(0, Math.min(1, y));
    if (action !== 'cancel') this.fence.set({
      enabled: true, x: Math.min(drag.x, cx), y: Math.min(drag.y, cy),
      width: Math.abs(cx - drag.x), height: Math.abs(cy - drag.y),
    });
    if (action === 'move') return;
    if (action === 'cancel' || this.fence().width < .01 || this.fence().height < .01) {
      this.fence.set(drag.previous);
      this.notice.set('Marcação cancelada ou muito pequena. Use no mínimo 1% em cada dimensão.');
    } else this.notice.set('Prévia pronta. Salve as posições para aplicar ao monitoramento.');
    this.drag = null;
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
  }

  async saveFence() {
    if (this.drag || this.fenceLoading() || this.saving()) return;
    const fence = this.fence();
    if (fence.width < .01 || fence.height < .01) { this.error.set('A cerca deve ter ao menos 1% em cada dimensão.'); return; }
    this.saving.set(true); this.error.set('');
    try {
      const result = await firstValueFrom(this.api.saveCameraFence(fence));
      this.savedFence.set(result.fence); this.fence.set({ ...result.fence }); this.editing.set(false);
      this.notice.set('Posições da cerca salvas no servidor. Inicie com a pessoa dentro da área.');
    } catch (error) { this.fail(error); }
    finally { this.saving.set(false); }
  }

  async startMonitoring() {
    if (!this.canStart()) { this.error.set('Abra a câmera e salve a cerca antes de iniciar.'); return; }
    const savedFence = this.savedFence();
    if (!savedFence) return;
    const generation = this.generation;
    this.starting.set(true); this.error.set('');
    this.alerts.set([]); this.events.set([]); this.state.set(null); this.elapsed.set(0);
    try {
      const microphone = await navigator.mediaDevices.getUserMedia({ video: false, audio: true });
      if (generation !== this.generation || this.destroyed) {
        microphone.getTracks().forEach(track => track.stop()); return;
      }
      microphone.getAudioTracks().forEach(track => this.stream?.addTrack(track));
      microphone.getAudioTracks().forEach(track => track.addEventListener('ended', () => {
        this.error.set('Microfone desconectado. Monitoramento interrompido.');
        void this.stopMonitoring();
      }));
      const context = new AudioContext({ sampleRate: 16000 });
      this.audioContext = context;
      await context.audioWorklet.addModule('/camera-audio-processor.js');
      if (generation !== this.generation || this.destroyed) return;
      await context.resume();
      if (generation !== this.generation || this.destroyed) return;
      this.audioNode = new AudioWorkletNode(context, 'camera-audio-processor');
      this.audioSource = context.createMediaStreamSource(microphone);
      await this.enableSound();
      const state = await firstValueFrom(this.api.createCameraMonitor(savedFence, this.record()));
      if (generation !== this.generation || this.destroyed) {
        await firstValueFrom(this.api.closeCameraMonitor(state.id)); return;
      }
      this.startedAt = performance.now(); this.audioOffset = 0; this.audioSamples = 0; this.queuedAudio = 0;
      this.state.set(state); this.active.set(true);
      this.audioNode.port.onmessage = ({ data }: MessageEvent<unknown>) => {
        if (typeof data !== 'object' || data === null) return;
        if ('flushed' in data) { this.flushResolve?.(); this.flushResolve = null; return; }
        if ('samples' in data && data.samples instanceof Float32Array) {
          this.queueAudio(data.samples, context.sampleRate, state.id);
        }
      };
      this.audioNode.onprocessorerror = () => {
        this.error.set('Captura de áudio interrompida. Reinicie o monitoramento.');
        void this.stopMonitoring();
      };
      this.audioSource.connect(this.audioNode); this.audioNode.connect(context.destination);
      this.frameRequest = this.captureFrame(state.id, generation);
    } catch (error) {
      this.fail(error);
      if (generation === this.generation) await this.stopMonitoring();
    }
    finally { if (generation === this.generation) this.starting.set(false); }
  }

  private queueAudio(samples: Float32Array, rate: number, id: string) {
    const timestamp = this.audioOffset + this.audioSamples / rate;
    this.audioSamples += samples.length;
    if (++this.queuedAudio > 5) {
      this.error.set('Análise de áudio não acompanha a captura. Monitoramento interrompido para evitar perda silenciosa.');
      void this.stopMonitoring(); return;
    }
    const blob = cameraWav(samples, rate);
    this.audioQueue = this.audioQueue.then(async () => {
      try { this.merge(await firstValueFrom(this.api.cameraAudio(id, blob, timestamp).pipe(timeout(60000))), 'audio'); }
      catch (error) { this.fail(error); void this.stopMonitoring(); }
      finally { this.queuedAudio--; }
    });
  }

  private async captureFrame(id: string, generation: number): Promise<void> {
    if (!this.active() || generation !== this.generation) return;
    try {
      const player = this.player()?.nativeElement;
      if (!player?.videoWidth || !player.videoHeight) throw new Error('Imagem da câmera indisponível.');
      const canvas = document.createElement('canvas');
      const scale = Math.min(1, 1280 / player.videoWidth);
      canvas.width = Math.round(player.videoWidth * scale); canvas.height = Math.round(player.videoHeight * scale);
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('Não foi possível capturar a imagem.');
      ctx.drawImage(player, 0, 0, canvas.width, canvas.height);
      const timestamp = (performance.now() - this.startedAt) / 1000;
      const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(
        b => b ? resolve(b) : reject(new Error('Falha ao codificar a imagem.')), 'image/jpeg', .85,
      ));
      if (!this.active() || generation !== this.generation) return;
      const state = await firstValueFrom(this.api.cameraFrame(id, blob, timestamp).pipe(timeout(60000)));
      if (generation !== this.generation) return;
      this.elapsed.set((performance.now() - this.startedAt) / 1000);
      this.merge(state, 'image');
      if (this.active()) this.frameTimer = setTimeout(() => {
        this.frameRequest = this.captureFrame(id, generation);
      }, 200);
    } catch (error) { this.fail(error); void this.stopMonitoring(); }
  }

  private merge(state: CameraMonitorState, source: 'image' | 'audio') {
    const current = this.state();
    this.state.set(source === 'image'
      ? { ...state, transcripts: current?.transcripts ?? state.transcripts,
        partial_text: current?.partial_text ?? state.partial_text }
      : { ...state, frame: current?.frame ?? state.frame, frame_count: current?.frame_count ?? state.frame_count });
    this.events.update(current => {
      const merged = new Map(current.map(e => [`${e.source}:${e.timestamp}:${e.kind}`, e]));
      for (const event of state.events) merged.set(`${event.source}:${event.timestamp}:${event.kind}`, event);
      return [...merged.values()].sort((a, b) => a.timestamp - b.timestamp);
    });
    this.mergeAlerts(state.alerts);
    if (state.audio_error) this.error.set(`Áudio: ${state.audio_error}`);
    if (state.audio_error && this.active()) void this.stopMonitoring();
  }

  private mergeAlerts(records: MonitorAlert[]) {
    this.alerts.update(current => {
      const merged = new Map(current.map(a => [a.id, a]));
      for (const alert of records) if ((merged.get(alert.id)?.version ?? 0) <= alert.version) merged.set(alert.id, alert);
      return [...merged.values()];
    });
  }

  async stopMonitoring() {
    if (this.stopping()) return;
    this.stopping.set(true); this.active.set(false);
    if (this.frameTimer) clearTimeout(this.frameTimer);
    this.frameTimer = null;
    this.audioSource?.disconnect(); this.audioSource = null;
    try {
      if (this.audioNode && this.audioContext?.state === 'running') {
        await new Promise<void>((resolve, reject) => {
          const timeout = setTimeout(() => { this.flushResolve = null; reject(new Error('Não foi possível finalizar a captura de áudio.')); }, 2000);
          this.flushResolve = () => { clearTimeout(timeout); resolve(); };
          this.audioNode?.port.postMessage('flush');
        });
      }
    } catch (error) { this.fail(error); }
    if (this.audioNode) {
      this.audioNode.port.onmessage = null;
      this.audioNode.disconnect();
    }
    this.audioNode = null;
    try { await this.audioContext?.close(); } catch (error) { this.fail(error); }
    this.audioContext = null;
    this.stream?.getAudioTracks().forEach(track => { track.stop(); this.stream?.removeTrack(track); });
    await this.frameRequest; await this.audioQueue;
    const state = this.state();
    if (state && !state.closed) {
      try {
        const closed = await firstValueFrom(this.api.closeCameraMonitor(state.id).pipe(timeout(60000)));
        this.state.set(closed); this.mergeAlerts(closed.alerts);
        this.notice.set(closed.recording_id ? 'Sessão encerrada. Gravação salva na biblioteca de vídeos de leito.'
          : 'Sessão encerrada. Cerca e histórico preservados; sem gravação de vídeo.');
        await this.loadHistory();
      } catch (error) { this.fail(error); }
    }
    this.stopping.set(false);
  }

  async disconnect() {
    this.generation++;
    const stream = this.stream;
    this.stream = null;
    const player = this.player()?.nativeElement;
    if (player && stream) { player.pause(); player.srcObject = null; }
    stream?.getTracks().forEach(track => track.stop());
    this.preview.set(false); this.starting.set(false);
    await this.stopMonitoring();
  }

  async acknowledge() {
    const state = this.state(), ids = this.pending().slice(0, 100).map(a => a.id);
    if (!state || !ids.length || this.acknowledging()) return;
    this.acknowledging.set(true);
    try {
      this.mergeAlerts(await firstValueFrom(this.api.acknowledgeCameraAlerts(state.id, ids)));
      if (!this.pending().length) this.stopBeep();
      await this.loadHistory();
    } catch (error) { this.fail(error); }
    finally { this.acknowledging.set(false); }
  }

  async loadHistory() {
    try { this.history.set(await firstValueFrom(this.api.cameraAlertLog())); }
    catch (error) { this.fail(error); }
  }

  async enableSound() {
    try {
      this.beepContext ??= new AudioContext();
      await this.beepContext.resume();
      if (this.beepContext.state !== 'running') throw new Error('Permita o áudio para ouvir os alertas.');
      this.soundError.set('');
    } catch (error) { this.soundError.set(error instanceof Error ? error.message : 'Não foi possível ativar o som.'); }
  }

  private startBeep() {
    if (this.beepTimer) return;
    const beep = () => {
      if (this.beepContext?.state !== 'running') return;
      const oscillator = this.beepContext.createOscillator(), gain = this.beepContext.createGain();
      oscillator.frequency.value = 880; gain.gain.value = .08;
      oscillator.connect(gain); gain.connect(this.beepContext.destination);
      oscillator.start(); oscillator.stop(this.beepContext.currentTime + .15);
      oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
    };
    beep(); this.beepTimer = setInterval(beep, 1000);
  }
  private stopBeep() { if (this.beepTimer) clearInterval(this.beepTimer); this.beepTimer = null; }
  private fail(error: unknown) {
    const detail: unknown = error instanceof HttpErrorResponse ? error.error?.detail : null;
    this.error.set(typeof detail === 'string' ? detail : error instanceof Error ? error.message : 'Falha no monitoramento. Consulte o servidor.');
  }
}
