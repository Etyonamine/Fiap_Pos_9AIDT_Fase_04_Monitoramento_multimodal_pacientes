import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, effect, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

interface SyntheticEvent {
  kind: string;
  message: string;
}

interface SyntheticSample {
  sample_id: string;
  timestamp: number;
  values: {
    heart_rate_bpm: number;
    systolic_mmhg: number;
    diastolic_mmhg: number;
    spo2_percent: number;
    medication: string;
    dose: number;
    unit: string;
    expected_regimen?: { dose: number; unit: string; status: string };
    synthetic_note?: string;
    note_evolution?: {
      introduced: { term: string; severity: string }[];
      persisted: { term: string; severity: string }[];
      resolved: { term: string; severity: string }[];
      notice: string;
    };
  };
  events: SyntheticEvent[];
  media_matches: { id: string; timestamp: number; modalities: string[] }[];
  delivery_status: 'sending' | 'delivered' | 'failed' | null;
  delivery_error: string | null;
}

interface SyntheticStreamResult {
  session_id: string;
  samples: SyntheticSample[];
  notice: string;
}

@Component({
  selector: 'app-synthetic-stream',
  templateUrl: './synthetic-stream.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SyntheticStream {
  readonly sessionId = input<string | null>(null);
  readonly elapsed = input(0);
  readonly closed = input(false);
  readonly running = signal(false);
  readonly busy = signal(false);
  readonly noteDraft = signal('');
  readonly error = signal('');
  readonly result = signal<SyntheticStreamResult | null>(null);
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  private timer: ReturnType<typeof setInterval> | null = null;
  private generation = 0;

  constructor() {
    effect(() => {
      this.sessionId();
      this.stop();
      this.generation++;
      this.busy.set(false);
      this.result.set(null);
      this.error.set('');
      this.noteDraft.set('');
    });
    effect(() => {
      if (this.closed()) this.stop();
    });
    this.destroyRef.onDestroy(() => this.stop());
  }

  start(): void {
    const id = this.sessionId();
    if (!id || this.closed() || this.busy()) return;
    this.error.set('');
    this.busy.set(true);
    const generation = this.generation;
    this.http.get<SyntheticStreamResult>(this.url(id)).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => {
        if (generation !== this.generation) return;
        this.result.set(result);
        this.busy.set(false);
        if (this.closed()) return;
        this.running.set(true);
        this.sendSample();
        this.timer = setInterval(() => this.sendSample(), 5000);
      },
      error: (error: HttpErrorResponse) => this.fail(error, generation),
    });
  }

  stop(): void {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    this.running.set(false);
  }

  retry(sample: SyntheticSample): void {
    const id = this.sessionId();
    if (!id || this.busy()) return;
    this.busy.set(true);
    const generation = this.generation;
    this.http.post<SyntheticStreamResult>(
      `${this.url(id)}/samples/${encodeURIComponent(sample.sample_id)}/retry`, {},
    ).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => {
        if (generation !== this.generation) return;
        this.busy.set(false);
        this.error.set('');
        this.result.set(result);
      },
      error: (error: HttpErrorResponse) => this.fail(error, generation),
    });
  }

  setNote(event: Event): void {
    this.noteDraft.set((event.target as HTMLTextAreaElement).value.slice(0, 1200));
  }

  termsLabel(items: { term: string }[]): string {
    return items.length ? items.map((item) => item.term).join(', ') : 'nenhuma';
  }

  refresh(): void {
    const id = this.sessionId();
    if (!id || this.busy()) return;
    this.busy.set(true);
    const generation = this.generation;
    this.http.get<SyntheticStreamResult>(this.url(id)).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => {
        if (generation !== this.generation) return;
        this.busy.set(false);
        this.error.set('');
        this.result.set(result);
      },
      error: (error: HttpErrorResponse) => this.fail(error, generation),
    });
  }

  private sendSample(): void {
    const id = this.sessionId();
    const timestamp = Math.floor(this.elapsed());
    const samples = this.result()?.samples ?? [];
    if (!id || this.closed() || this.busy()) return;
    if (samples.length && timestamp <= samples[0].timestamp) {
      this.refresh();
      return;
    }
    this.busy.set(true);
    const generation = this.generation;
    this.http.post<SyntheticStreamResult>(`${this.url(id)}/samples`, {
      sample_id: crypto.randomUUID(), timestamp,
      scenario: samples.length ? 'change' : 'stable',
      note: this.noteDraft().trim() || undefined,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => {
        if (generation !== this.generation) return;
        this.busy.set(false);
        this.result.set(result);
      },
      error: (error: HttpErrorResponse) => this.fail(error, generation),
    });
  }

  private url(id: string): string {
    return `/api/synthetic-stream/${encodeURIComponent(id)}`;
  }

  private fail(error: HttpErrorResponse, generation: number): void {
    if (generation !== this.generation) return;
    this.busy.set(false);
    this.stop();
    this.error.set(typeof error.error?.detail === 'string'
      ? error.error.detail : `Falha no simulador sintético (HTTP ${error.status || 'indisponível'}).`);
  }
}
