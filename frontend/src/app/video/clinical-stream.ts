import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, effect, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, exhaustMap, timer } from 'rxjs';
import { catchError, tap } from 'rxjs/operators';
import type { PlanComparison } from '../telemetry/clinical-data-api';

interface ClinicalStreamEvent {
  source: 'vitals' | 'prescriptions';
  kind: string;
  field?: string;
  message: string;
  priority: 'review' | 'information';
  delivery_id: string | null;
  delivery: {
    status: 'pending' | 'sending' | 'delivered' | 'failed' | 'cancelled';
    last_error: string | null;
    http_status: number | null;
    attempts: number;
    delivered_at: string | null;
  } | null;
}

interface ClinicalStreamSample {
  sample_id: string;
  source_id: string;
  recorded_at: string;
  elapsed_seconds: number;
  vitals: {
    heart_rate_bpm?: number;
    systolic_mmhg?: number;
    diastolic_mmhg?: number;
    spo2_percent?: number;
  };
  prescriptions: {
    medication: string;
    dose: number;
    unit: string;
    status: 'active' | 'discontinued';
    route?: string;
    frequency?: string;
    expected_regimen?: {
      dose: number;
      unit: string;
      status: 'active' | 'discontinued';
      route?: string;
      frequency?: string;
    };
    plan_comparison?: PlanComparison;
  }[];
  events: ClinicalStreamEvent[];
  media_matches: { timestamp: number; modalities: string[] }[];
}

interface ClinicalStreamResult {
  session_id: string;
  samples: ClinicalStreamSample[];
  notice: string;
}

@Component({
  selector: 'app-clinical-stream',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './clinical-stream.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ClinicalStream {
  readonly sessionId = input<string | null>(null);
  readonly active = input(false);
  readonly closed = input(true);
  readonly result = signal<ClinicalStreamResult | null>(null);
  readonly error = signal('');
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);

  constructor() {
    effect((onCleanup) => {
      const sessionId = this.sessionId();
      if (!sessionId || !this.active() || this.closed()) {
        this.result.set(null);
        this.error.set('');
        return;
      }
      const poll = timer(0, 2000).pipe(
        exhaustMap(() => this.http.get<ClinicalStreamResult>(
          `/api/clinical-stream/${encodeURIComponent(sessionId)}`,
        ).pipe(
          tap((result) => {
            this.result.set(result);
            this.error.set('');
          }),
          catchError((error: HttpErrorResponse) => {
            this.error.set(this.errorMessage(error));
            return EMPTY;
          }),
        )),
        takeUntilDestroyed(this.destroyRef),
      ).subscribe();
      onCleanup(() => poll.unsubscribe());
    });
  }

  sourceLabel(source: ClinicalStreamEvent['source']): string {
    return source === 'vitals' ? 'Sinais vitais' : 'Prescrição';
  }

  deliveryLabel(event: ClinicalStreamEvent): string {
    if (event.priority === 'information') return 'Alteração prevista: webhook não acionado.';
    if (!event.delivery) return 'Webhook desativado ou não configurado';
    const labels: Record<NonNullable<ClinicalStreamEvent['delivery']>['status'], string> = {
      pending: 'Entrega pendente',
      sending: 'Enviando alerta',
      delivered: 'Aceito pelo destino',
      failed: 'Falha na entrega',
      cancelled: 'Entrega cancelada',
    };
    return labels[event.delivery.status];
  }

  private errorMessage(error: HttpErrorResponse): string {
    const detail: unknown = error.error?.detail;
    return typeof detail === 'string'
      ? detail
      : `Falha ao consultar amostras clínicas (HTTP ${error.status || 'indisponível'}).`;
  }
}
