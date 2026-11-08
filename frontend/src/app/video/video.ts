import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  ElementRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { EMPTY, Subject, catchError, switchMap, takeWhile, timer } from 'rxjs';
import { AnalysisMode, ClinicalVideo, Fence, FrameMetadata, VideoApi } from './video-api';
import type { VideoEvent } from './video-api';

const BONES = [
  [5, 6],
  [5, 7],
  [7, 9],
  [6, 8],
  [8, 10],
  [5, 11],
  [6, 12],
  [11, 12],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
];

@Component({
  selector: 'app-video',
  imports: [RouterLink],
  templateUrl: './video.html',
  styleUrl: './video.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Video {
  private readonly api = inject(VideoApi);
  private readonly destroyRef = inject(DestroyRef);
  readonly player = viewChild<ElementRef<HTMLVideoElement>>('player');
  readonly canvas = viewChild<ElementRef<HTMLCanvasElement>>('overlay');
  readonly log = viewChild<ElementRef<HTMLElement>>('eventLog');
  readonly mode = signal<AnalysisMode>('bed');
  readonly videos = signal<ClinicalVideo[]>([]);
  readonly selected = signal<ClinicalVideo | null>(null);
  readonly metadata = signal<FrameMetadata | null>(null);
  readonly events = signal<VideoEvent[]>([]);
  readonly currentTime = signal(0);
  readonly error = signal('');
  readonly uploading = signal(false);
  readonly savingFence = signal(false);
  readonly editingFence = signal(false);
  readonly fenceDraft = signal<Fence>({ enabled: true, x: 0.1, y: 0.1, width: 0.8, height: 0.8 });
  readonly sources = computed(() => this.videos().filter((video) => video.mode === this.mode()));
  readonly busy = computed(() => {
    const status = this.selected()?.status;
    return this.uploading() || this.savingFence() || status === 'queued' || status === 'processing';
  });
  readonly activeEvent = computed(() => {
    let index = -1;
    this.events().forEach((event, i) => {
      if (event.timestamp <= this.currentTime()) index = i;
    });
    return index;
  });
  readonly telemetry = computed(() => this.metadata()?.people[0] ?? null);
  private readonly selections = new Subject<ClinicalVideo>();
  private readonly frameRequests = new Subject<{ id: string; timestamp: number } | null>();
  private callbackId: number | null = null;
  private lastFrame = -1;
  private lastActiveEvent = -2;

  constructor() {
    this.api
      .list()
      .pipe(takeUntilDestroyed())
      .subscribe({
        next: (videos) => this.videos.set(videos),
        error: (error) => this.showError(error),
      });
    this.selections
      .pipe(
        switchMap((video) =>
          timer(0, 1000).pipe(
            switchMap(() => this.api.status(video.id)),
            takeWhile((value) => value.status === 'queued' || value.status === 'processing', true),
            catchError((error) => {
              this.showError(error);
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(),
      )
      .subscribe((video) => {
        this.selected.set(video);
        this.videos.update((videos) => videos.map((item) => (item.id === video.id ? video : item)));
        if (video.status === 'ready') {
          this.fenceDraft.set({ ...video.fence });
          this.loadEvents(video.id);
        }
        if (video.status === 'failed') this.error.set(video.error ?? 'Falha no processamento.');
      });
    this.frameRequests
      .pipe(
        switchMap((request) =>
          request
            ? this.api.frame(request.id, request.timestamp).pipe(
                catchError((error) => {
                  this.showError(error);
                  return EMPTY;
                }),
              )
            : EMPTY,
        ),
        takeUntilDestroyed(),
      )
      .subscribe((frame) => {
        const video = this.selected();
        if (!video || Math.floor(frame.timestamp * video.fps + 1e-6) !== this.lastFrame) return;
        this.metadata.set(frame);
        this.draw(frame);
      });
    this.destroyRef.onDestroy(() => this.cancelCallback());
  }

  changeMode(mode: AnalysisMode) {
    if (this.uploading() || this.savingFence()) return;
    this.mode.set(mode);
  }

  upload(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    if (file.size > 500 * 1024 * 1024) {
      this.error.set('O limite por vídeo é 500 MB.');
      return;
    }
    this.error.set('');
    this.uploading.set(true);
    this.api
      .upload(file, this.mode())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (video) => {
          this.uploading.set(false);
          this.videos.update((videos) => [video, ...videos]);
          this.select(video);
        },
        error: (error) => {
          this.uploading.set(false);
          this.showError(error);
        },
      });
  }

  select(video: ClinicalVideo) {
    if (this.savingFence() || this.uploading()) return;
    this.player()?.nativeElement.pause();
    this.cancelCallback();
    this.frameRequests.next(null);
    this.selected.set(video);
    this.mode.set(video.mode);
    this.error.set('');
    this.events.set([]);
    this.currentTime.set(0);
    this.lastFrame = -1;
    this.lastActiveEvent = -2;
    this.editingFence.set(false);
    this.clearOverlay();
    this.selections.next(video);
  }

  onLoaded() {
    this.lastFrame = -1;
    this.sync();
  }

  onPlay() {
    const player = this.player()?.nativeElement;
    if (!player || this.callbackId !== null) return;
    const next = (_now: number, frame: VideoFrameCallbackMetadata) => {
      this.callbackId = null;
      this.sync(frame.mediaTime);
      if (!player.paused && !player.ended) this.callbackId = player.requestVideoFrameCallback(next);
    };
    this.callbackId = player.requestVideoFrameCallback(next);
  }

  onPause() {
    this.cancelCallback();
    this.sync();
  }

  onSeeking() {
    this.lastFrame = -1;
    this.frameRequests.next(null);
    this.clearOverlay();
    this.sync();
  }

  sync(displayedTime?: number) {
    const player = this.player()?.nativeElement;
    const video = this.selected();
    if (!player || !video || video.status !== 'ready' || this.savingFence()) return;
    // During playback the presented frame, not the coarse timeupdate event, owns the overlay.
    if (
      displayedTime === undefined &&
      !player.paused &&
      !player.seeking &&
      this.callbackId !== null
    )
      return;
    const time = displayedTime ?? player.currentTime;
    this.currentTime.set(time);
    const frame = Math.min(
      Math.floor(time * video.fps + 1e-6),
      Math.ceil(video.duration * video.fps) - 1,
    );
    if (frame !== this.lastFrame) {
      this.lastFrame = frame;
      this.clearOverlay();
      this.frameRequests.next({ id: video.id, timestamp: Math.min(time, video.duration) });
    }
    const index = this.activeEvent();
    if (index !== this.lastActiveEvent) {
      this.lastActiveEvent = index;
      const log = this.log()?.nativeElement;
      const row = log?.querySelector<HTMLElement>(`[data-event-index="${index}"]`);
      if (log && row)
        log.scrollTop += row.getBoundingClientRect().top - log.getBoundingClientRect().top - 40;
      else if (log) log.scrollTop = 0;
    }
  }

  seek(timestamp: number) {
    const player = this.player()?.nativeElement;
    if (player) player.currentTime = timestamp;
  }

  togglePause() {
    const player = this.player()?.nativeElement;
    if (!player) return;
    if (player.paused) void player.play().catch((error) => this.showError(error));
    else player.pause();
  }

  editFence() {
    const video = this.selected();
    if (!video) return;
    this.player()?.nativeElement.pause();
    this.fenceDraft.set({ ...video.fence });
    this.editingFence.set(!this.editingFence());
    const frame = this.metadata();
    if (frame) this.draw(frame);
  }

  changeFence(key: 'x' | 'y' | 'width' | 'height', event: Event) {
    const value = Number((event.target as HTMLInputElement).value) / 100;
    this.fenceDraft.update((fence) => {
      const next = { ...fence, [key]: value };
      next.width = Math.min(next.width, 1 - next.x);
      next.height = Math.min(next.height, 1 - next.y);
      return next;
    });
    const frame = this.metadata();
    if (frame) this.draw(frame);
  }

  allowForwardMovement() {
    this.fenceDraft.update((fence) => ({ ...fence, y: 0.15, height: 0.85 }));
    const frame = this.metadata();
    if (frame) this.draw(frame);
  }

  saveFence(toggle = false) {
    const video = this.selected();
    if (!video || this.savingFence()) return;
    this.player()?.nativeElement.pause();
    const fence = toggle ? { ...video.fence, enabled: !video.fence.enabled } : this.fenceDraft();
    this.savingFence.set(true);
    this.frameRequests.next(null);
    this.clearOverlay();
    this.api
      .fence(video.id, fence)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.selected.set(updated);
          this.fenceDraft.set({ ...updated.fence });
          this.editingFence.set(false);
          this.savingFence.set(false);
          this.loadEvents(video.id);
          this.lastFrame = -1;
          this.sync();
        },
        error: (error) => {
          this.savingFence.set(false);
          this.showError(error);
          this.lastFrame = -1;
          this.sync();
        },
      });
  }

  downloadReport() {
    const video = this.selected();
    if (!video) return;
    this.api
      .report(video.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (report) => {
          const url = URL.createObjectURL(
            new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }),
          );
          const link = document.createElement('a');
          link.href = url;
          link.download = `analise-${video.id}.json`;
          link.click();
          URL.revokeObjectURL(url);
        },
        error: (error) => this.showError(error),
      });
  }

  timecode(time: number) {
    const seconds = Math.floor(time);
    return `${Math.floor(seconds / 60)
      .toString()
      .padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
  }

  mediaError() {
    this.error.set(
      'Não foi possível reproduzir o vídeo. Verifique o servidor e o formato do arquivo.',
    );
  }

  private loadEvents(id: string) {
    this.api
      .events(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (events) => {
          if (this.selected()?.id !== id) return;
          this.events.set(events);
          this.lastActiveEvent = -2;
          this.sync();
        },
        error: (error) => this.showError(error),
      });
  }

  private cancelCallback() {
    if (this.callbackId !== null)
      this.player()?.nativeElement.cancelVideoFrameCallback(this.callbackId);
    this.callbackId = null;
  }

  private clearOverlay() {
    this.metadata.set(null);
    const canvas = this.canvas()?.nativeElement;
    canvas?.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height);
  }

  private draw(frame: FrameMetadata) {
    const canvas = this.canvas()?.nativeElement;
    const video = this.selected();
    if (!canvas || !video) return;
    canvas.width = video.width;
    canvas.height = video.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.lineWidth = Math.max(2, video.width / 400);
    const fence = this.editingFence() ? this.fenceDraft() : frame.fence;
    if (fence.enabled) {
      ctx.strokeStyle = '#f97316';
      ctx.fillStyle = '#f9731620';
      ctx.setLineDash([10, 6]);
      ctx.fillRect(
        fence.x * canvas.width,
        fence.y * canvas.height,
        fence.width * canvas.width,
        fence.height * canvas.height,
      );
      ctx.strokeRect(
        fence.x * canvas.width,
        fence.y * canvas.height,
        fence.width * canvas.width,
        fence.height * canvas.height,
      );
      ctx.setLineDash([]);
    }
    for (const person of frame.people) {
      ctx.strokeStyle = '#3b82f6';
      const [x, y, width, height] = person.box;
      ctx.strokeRect(
        x * canvas.width,
        y * canvas.height,
        width * canvas.width,
        height * canvas.height,
      );
      ctx.strokeStyle = '#14b8a6';
      ctx.fillStyle = '#14b8a6';
      for (const [a, b] of BONES) {
        const start = person.keypoints[a];
        const end = person.keypoints[b];
        if (!start || !end || start[2] < 0.5 || end[2] < 0.5) continue;
        ctx.beginPath();
        ctx.moveTo(start[0] * canvas.width, start[1] * canvas.height);
        ctx.lineTo(end[0] * canvas.width, end[1] * canvas.height);
        ctx.stroke();
      }
      for (const [px, py, confidence] of person.keypoints) {
        if (confidence < 0.5) continue;
        ctx.beginPath();
        ctx.arc(px * canvas.width, py * canvas.height, ctx.lineWidth * 2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  private showError(error: unknown) {
    const detail: unknown = error instanceof HttpErrorResponse ? error.error?.detail : null;
    this.error.set(
      typeof detail === 'string'
        ? detail
        : error instanceof HttpErrorResponse && error.status === 0
          ? 'Servidor indisponível. Inicie o FastAPI e verifique o proxy /api.'
          : 'Não foi possível concluir a operação. Consulte o log do servidor.',
    );
  }
}
