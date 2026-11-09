import { DatePipe, DecimalPipe, PercentPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  computed,
  DestroyRef,
  ElementRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { Subscription, timer } from 'rxjs';
import { exhaustMap } from 'rxjs/operators';
import {
  AudioApi,
  AudioConfiguration,
  AudioStatus,
  ClinicalAudio,
  SentimentLabel,
} from './audio-api';

@Component({
  selector: 'app-voice',
  imports: [RouterLink, DatePipe, DecimalPipe, PercentPipe],
  templateUrl: './voice.html',
  styleUrl: './voice.scss',
})
export class Voice {
  private readonly api = inject(AudioApi);
  private readonly destroyRef = inject(DestroyRef);
  private polling?: Subscription;
  private autoAnalyzeId: string | null = null;
  readonly player = viewChild<ElementRef<HTMLAudioElement>>('player');
  readonly audios = signal<ClinicalAudio[]>([]);
  readonly selected = signal<ClinicalAudio | null>(null);
  readonly configuration = signal<AudioConfiguration | null>(null);
  readonly error = signal('');
  readonly uploading = signal(false);
  readonly requesting = signal(false);
  readonly consent = signal(false);
  readonly currentTime = signal(0);
  readonly busy = computed(() => {
    const status = this.selected()?.status;
    return (
      this.uploading() ||
      this.requesting() ||
      status === 'importing' ||
      status === 'queued' ||
      status === 'analyzing'
    );
  });
  readonly waveform = computed(() => {
    const bars = this.selected()?.acoustic?.waveform ?? [];
    const maximum = Math.max(...bars, 0.001);
    return bars.map((bar) => Math.max(2, (bar / maximum) * 100));
  });
  readonly activeSegment = computed(() => {
    const segments = this.selected()?.result?.transcription.segments ?? [];
    return segments.findIndex(
      (segment) =>
        this.currentTime() >= segment.offset &&
        this.currentTime() < segment.offset + segment.duration,
    );
  });
  readonly statusLabels: Record<AudioStatus, string> = {
    importing: 'Importando',
    uploaded: 'Pronto para analisar',
    queued: 'Na fila',
    analyzing: 'Analisando no Azure',
    ready: 'Análise concluída',
    failed: 'Falha no processamento',
  };
  readonly sentimentLabels: Record<SentimentLabel, string> = {
    positive: 'Positivo',
    neutral: 'Neutro',
    negative: 'Negativo',
    mixed: 'Misto',
  };

  constructor() {
    this.reload();
    this.api
      .configuration()
      .pipe(takeUntilDestroyed())
      .subscribe({
        next: (config) => this.configuration.set(config),
        error: (error: HttpErrorResponse) => this.showError(error),
      });
    this.destroyRef.onDestroy(() => this.polling?.unsubscribe());
  }

  reload() {
    this.api
      .list()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (audios) => {
          this.audios.set(audios);
          const current = audios.find((audio) => audio.id === this.selected()?.id);
          if (current) this.select(current);
          else if (!this.selected() && audios.length) this.select(audios[0]);
        },
        error: (error: HttpErrorResponse) => this.showError(error),
      });
  }

  select(audio: ClinicalAudio) {
    this.polling?.unsubscribe();
    this.player()?.nativeElement.pause();
    this.selected.set(audio);
    this.currentTime.set(0);
    this.error.set('');
    this.poll(audio);
  }

  upload(event: Event) {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    const file = input.files?.[0];
    input.value = '';
    if (!file || this.busy() || !this.consent()) return;
    if (!/\.(wav|mp3|m4a|ogg|flac|webm|aac)$/i.test(file.name)) {
      this.error.set('Envie WAV, MP3, M4A, OGG, FLAC, WebM ou AAC.');
      return;
    }
    if (!file.size || file.size > 100 * 1024 * 1024) {
      this.error.set('Envie um arquivo não vazio de até 100 MB.');
      return;
    }
    this.uploading.set(true);
    this.error.set('');
    this.api
      .upload(file)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (audio) => {
          this.uploading.set(false);
          this.update(audio);
          this.autoAnalyzeId = ['importing', 'uploaded'].includes(audio.status) ? audio.id : null;
          this.select(audio);
          this.startAutomaticAnalysis(audio);
        },
        error: (error: HttpErrorResponse) => {
          this.uploading.set(false);
          this.showError(error);
        },
      });
  }

  analyze() {
    const audio = this.selected();
    if (!audio?.url || this.busy() || !this.consent()) return;
    this.error.set('');
    this.requesting.set(true);
    this.api
      .analyze(audio.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.requesting.set(false);
          this.update(updated);
          this.poll(updated);
        },
        error: (error: HttpErrorResponse) => {
          this.requesting.set(false);
          this.showError(error);
        },
      });
  }

  autoAnalyzing(audio: ClinicalAudio): boolean {
    return this.autoAnalyzeId === audio.id && audio.status === 'importing';
  }

  hasHighPriority(audio: ClinicalAudio): boolean {
    return (
      audio.result?.critical_terms.some(
        (mention) => mention.severity === 'critical' && !mention.negated,
      ) ?? false
    );
  }

  deleteSelected() {
    const audio = this.selected();
    if (!audio || this.busy()) return;
    this.requesting.set(true);
    this.api
      .delete(audio.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.requesting.set(false);
          this.polling?.unsubscribe();
          this.player()?.nativeElement.pause();
          this.audios.update((audios) => audios.filter((item) => item.id !== audio.id));
          this.selected.set(null);
          this.currentTime.set(0);
          this.error.set('');
        },
        error: (error: HttpErrorResponse) => {
          this.requesting.set(false);
          this.showError(error);
        },
      });
  }

  seek(offset: number) {
    const player = this.player()?.nativeElement;
    if (player) {
      player.currentTime = offset;
      this.currentTime.set(offset);
    }
  }

  sync() {
    this.currentTime.set(this.player()?.nativeElement.currentTime ?? 0);
  }

  mediaError() {
    this.error.set(
      'Não foi possível reproduzir o áudio. Confira a conexão e importe novamente se necessário.',
    );
  }

  time(seconds: number): string {
    return `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60)
      .toString()
      .padStart(2, '0')}`;
  }

  private update(audio: ClinicalAudio) {
    this.audios.update((audios) => {
      const others = audios.filter((item) => item.id !== audio.id);
      return [audio, ...others].sort((a, b) => b.created_at.localeCompare(a.created_at));
    });
    if (this.selected()?.id === audio.id) this.selected.set(audio);
  }

  private poll(audio: ClinicalAudio) {
    this.polling?.unsubscribe();
    if (!['importing', 'queued', 'analyzing'].includes(audio.status)) return;
    this.polling = timer(1000, 1500)
      .pipe(
        exhaustMap(() => this.api.status(audio.id)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (updated) => {
          if (this.selected()?.id !== audio.id) return;
          this.update(updated);
          this.startAutomaticAnalysis(updated);
          if (!['importing', 'queued', 'analyzing'].includes(updated.status)) {
            this.polling?.unsubscribe();
          }
        },
        error: (error: HttpErrorResponse) => {
          this.polling?.unsubscribe();
          this.showError(error);
        },
      });
  }

  private startAutomaticAnalysis(audio: ClinicalAudio) {
    if (this.autoAnalyzeId !== audio.id || audio.status !== 'uploaded') return;
    this.autoAnalyzeId = null;
    if (this.consent()) this.analyze();
  }

  private showError(error: HttpErrorResponse) {
    const detail: unknown = error.error?.detail;
    this.error.set(
      typeof detail === 'string'
        ? detail
        : 'Não foi possível acessar o módulo de áudio. Confira o backend e recarregue a biblioteca.',
    );
  }
}
