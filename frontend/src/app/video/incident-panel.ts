import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, input, output, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Incident, IncidentChange, MonitorAlert, VideoApi } from './video-api';

@Component({
  selector: 'app-incident-panel',
  imports: [DatePipe],
  templateUrl: './incident-panel.html',
  styleUrl: './incident-panel.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class IncidentPanel {
  readonly incidents = input<Incident[]>([]);
  readonly alerts = input<MonitorAlert[]>([]);
  readonly canSeek = input(false);
  readonly seekEvidence = output<number>();
  private readonly api = inject(VideoApi);
  private readonly destroyRef = inject(DestroyRef);
  readonly current = computed(() => this.incidents().filter(item => !item.merged_into));
  readonly history = signal<Incident[] | null>(null);
  readonly cursor = signal<number | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly audit = signal<IncidentChange[] | null>(null);
  readonly auditId = signal('');
  readonly auditCursor = signal<number | null>(null);
  readonly auditLoading = signal(false);

  evidence(incident: Incident) {
    const records = new Map(this.alerts().map(alert => [alert.id, alert]));
    return incident.evidence.map(item => {
      const current = records.get(item.id);
      return current && current.version > item.version ? { ...item, ...current } : item;
    });
  }

  acknowledged(incident: Incident) {
    const active = this.evidence(incident).filter(item => item.status !== 'retracted');
    return active.length > 0 && active.every(item => item.acknowledged_at);
  }

  loadHistory(more = false) {
    if (this.loading()) return;
    this.loading.set(true);
    this.error.set('');
    this.api.incidents(more ? this.cursor() ?? undefined : undefined)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: page => {
          this.history.update(current => more ? [...(current ?? []), ...page.items] : page.items);
          this.cursor.set(page.next_cursor);
          this.loading.set(false);
        },
        error: error => this.fail(error),
      });
  }

  loadAudit(id: string, more = false) {
    if (this.auditLoading()) return;
    this.auditLoading.set(true);
    this.auditId.set(id);
    if (!more) {
      this.audit.set(null);
      this.auditCursor.set(null);
    }
    this.error.set('');
    this.api.incidentHistory(id, more ? this.auditCursor() ?? undefined : undefined)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: page => {
          this.audit.update(current => more ? [...(current ?? []), ...page.items] : page.items);
          this.auditCursor.set(page.next_cursor);
          this.auditLoading.set(false);
        },
        error: error => this.fail(error),
      });
  }

  private fail(error: unknown) {
    this.loading.set(false);
    this.auditLoading.set(false);
    this.error.set(error instanceof HttpErrorResponse && typeof error.error?.detail === 'string'
      ? error.error.detail : 'Falha ao consultar o histórico de incidentes. Tente novamente.');
  }
}
