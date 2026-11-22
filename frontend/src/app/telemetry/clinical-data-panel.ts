import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { forkJoin } from 'rxjs';
import {
  ClinicalDataApi, ClinicalDataKind, ClinicalImport, FhirKind, MediaIncident,
  NotificationDelivery, NotificationStatus, VitalPoint,
} from './clinical-data-api';

interface TimelineItem {
  recordedAt: string;
  source: string;
  patient: string;
  description: string;
  priority: string;
}

@Component({
  selector: 'app-clinical-data-panel',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './clinical-data-panel.html',
  styleUrl: './clinical-data-panel.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ClinicalDataPanel {
  private readonly api = inject(ClinicalDataApi);
  readonly imports = signal<ClinicalImport[]>([]);
  readonly incidents = signal<MediaIncident[]>([]);
  readonly busy = signal(false);
  readonly consentToCloud = signal(false);
  readonly fhirPatientId = signal('');
  readonly fhirKind = signal<FhirKind>('vitals');
  readonly fhirAuthorized = signal(false);
  readonly notificationStatus = signal<NotificationStatus | null>(null);
  readonly notificationError = signal('');
  readonly retrying = signal('');
  readonly message = signal('');
  readonly error = signal('');
  readonly timeline = computed<TimelineItem[]>(() => {
    const imported = this.imports().flatMap((item) =>
      item.events.map((event) => ({
        recordedAt: event.recorded_at,
        source: item.kind === 'vitals' ? 'Sinais vitais'
          : item.kind === 'prescriptions' ? 'Prescrição' : 'Texto clínico',
        patient: event.patient_ref,
        description: event.message,
        priority: event.priority,
      })),
    );
    const media = this.incidents().flatMap((incident) =>
      incident.status === 'retracted' ? [] : incident.evidence
        .filter((evidence) => evidence.status !== 'retracted')
        .map((evidence) => ({
          recordedAt: incident.created_at,
          source: evidence.source === 'image' ? 'Vídeo/câmera' : 'Fala transcrita',
          patient: 'Sessão monitorada',
          description: evidence.text
            ? `${evidence.kind}: ${evidence.text}`
            : evidence.kind,
          priority: 'review',
        })),
    );
    return [...imported, ...media].sort((a, b) =>
      Date.parse(b.recordedAt) - Date.parse(a.recordedAt),
    );
  });

  constructor() {
    this.refresh();
  }

  refresh(): void {
    this.error.set('');
    this.refreshNotifications();
    forkJoin({
      imports: this.api.imports(),
      incidents: this.api.mediaIncidents(),
    }).subscribe({
      next: (result) => {
        this.imports.set(result.imports);
        this.incidents.set(result.incidents.items);
      },
      error: (error: HttpErrorResponse) => this.error.set(this.errorMessage(error)),
    });
  }

  refreshNotifications(): void {
    this.notificationError.set('');
    this.api.notifications().subscribe({
      next: (status) => this.notificationStatus.set(status),
      error: (error: HttpErrorResponse) => {
        this.notificationStatus.set(null);
        this.notificationError.set(this.errorMessage(error, 'notificações'));
      },
    });
  }

  retryNotification(id: string): void {
    if (this.retrying()) return;
    this.retrying.set(id);
    this.notificationError.set('');
    this.api.retryNotification(id).subscribe({
      next: () => {
        this.retrying.set('');
        this.refreshNotifications();
      },
      error: (error: HttpErrorResponse) => {
        this.retrying.set('');
        this.notificationError.set(this.errorMessage(error, 'notificações'));
      },
    });
  }

  notificationLabel(status: NotificationDelivery['status']): string {
    const labels: Record<NotificationDelivery['status'], string> = {
      pending: 'Pendente', sending: 'Enviando', delivered: 'Aceita pelo destino',
      failed: 'Falhou', cancelled: 'Cancelada',
    };
    return labels[status] ?? status;
  }

  setFhirPatientId(event: Event): void {
    this.fhirPatientId.set((event.target as HTMLInputElement).value);
  }

  setFhirKind(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    if (value === 'vitals' || value === 'prescriptions') this.fhirKind.set(value);
  }

  toggleFhirAuthorization(event: Event): void {
    this.fhirAuthorized.set((event.target as HTMLInputElement).checked);
  }

  importFhir(): void {
    const patientId = this.fhirPatientId().trim();
    if (!patientId || !this.fhirAuthorized()) {
      this.error.set('Informe o identificador FHIR e confirme a autorização para consulta.');
      return;
    }
    this.submit(
      () => this.api.importFhir(patientId, this.fhirKind(), true),
      'Consulta FHIR importada para revisão; o identificador não foi salvo.',
      () => {
        this.fhirPatientId.set('');
        this.fhirAuthorized.set(false);
      },
    );
  }

  upload(kind: 'vitals' | 'prescriptions', event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file || this.busy()) return;
    this.submit(() => this.api.upload(kind, file), `${file.name} analisado e registrado no histórico.`);
    (event.target as HTMLInputElement).value = '';
  }

  uploadNote(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file || this.busy()) return;
    if (!this.consentToCloud()) {
      this.error.set('Marque a autorização antes de enviar o texto ao Azure AI Language.');
      (event.target as HTMLInputElement).value = '';
      return;
    }
    this.submit(
      () => this.api.uploadNote(file, true),
      'Texto analisado pelo Azure AI Language; o original não foi persistido.',
    );
    (event.target as HTMLInputElement).value = '';
  }

  exampleUrl(kind: ClinicalDataKind): string {
    return `/api/clinical-data/examples/${kind === 'notes' ? 'note' : kind}`;
  }

  toggleConsent(event: Event): void {
    this.consentToCloud.set((event.target as HTMLInputElement).checked);
  }

  latestPoint(item: ClinicalImport): VitalPoint | undefined {
    return item.points?.at(-1);
  }

  eventCount(item: ClinicalImport): number {
    return item.events.length;
  }

  private submit(
    request: () => ReturnType<ClinicalDataApi['upload']> | ReturnType<ClinicalDataApi['uploadNote']>,
    success: string,
    onSuccess?: () => void,
  ): void {
    this.busy.set(true);
    this.error.set('');
    this.message.set('');
    request().subscribe({
      next: (record) => {
        this.imports.update((items) => [record, ...items.filter((item) => item.id !== record.id)]);
        this.message.set(success);
        this.busy.set(false);
        onSuccess?.();
        this.refresh();
      },
      error: (error: HttpErrorResponse) => {
        this.error.set(this.errorMessage(error));
        this.busy.set(false);
      },
    });
  }

  private errorMessage(error: HttpErrorResponse, context = 'dados clínicos'): string {
    const detail = error.error?.detail;
    return typeof detail === 'string'
      ? detail
      : `Falha ao carregar ${context} (HTTP ${error.status || 'indisponível'}).`;
  }
}
