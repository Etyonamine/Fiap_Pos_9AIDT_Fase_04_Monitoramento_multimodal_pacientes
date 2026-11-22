import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import type { KeyPhraseMention } from '../voice/audio-api';

export type ClinicalDataKind = 'vitals' | 'prescriptions' | 'notes';

export interface ClinicalImportEvent {
  recorded_at: string;
  patient_ref: string;
  kind: string;
  field?: string;
  medication?: string;
  message: string;
  priority: 'review' | 'information';
}

export interface PlanComparison {
  status: 'matches' | 'differs' | 'incomplete' | 'not_provided';
  compared_fields: string[];
  different_fields: string[];
  missing_fields?: string[];
}

export interface VitalPoint {
  recorded_at: string;
  patient_ref: string;
  heart_rate_bpm?: number;
  systolic_mmhg?: number;
  diastolic_mmhg?: number;
  spo2_percent?: number;
}

export type FhirKind = 'vitals' | 'prescriptions';

export interface ClinicalImport {
  id: string;
  kind: ClinicalDataKind;
  name: string;
  created_at: string;
  record_count: number;
  patient_count: number;
  events: ClinicalImportEvent[];
  points?: VitalPoint[];
  records?: {
    recorded_at: string;
    patient_ref: string;
    medication: string;
    dose: number | null;
    unit: string | null;
    status: 'active' | 'discontinued' | 'on-hold' | 'cancelled' | 'completed'
      | 'stopped' | 'draft' | 'unknown';
    route: string;
    frequency: string;
    expected_regimen?: {
      dose: number;
      unit: string;
      status: 'active' | 'discontinued';
      route?: string;
      frequency?: string;
    } | null;
    plan_comparison?: PlanComparison;
  }[];
  language?: {
    provider: string;
    key_phrases: string[];
    key_phrase_mentions?: KeyPhraseMention[];
    sentiment: {
      label: 'positive' | 'neutral' | 'negative' | 'mixed';
      scores: { positive: number; neutral: number; negative: number };
      aggregation: string;
    };
  };
  source?: string;
  warnings?: string[];
  notice?: string;
  rules?: {
    notice: string;
  };
}

export interface NotificationDelivery {
  id: string;
  source: 'image' | 'audio' | 'vitals' | 'prescriptions' | 'other';
  created_at: string;
  updated_at: string;
  status: 'pending' | 'sending' | 'delivered' | 'failed' | 'cancelled';
  attempts: number;
  last_error: string | null;
  http_status: number | null;
  delivered_at: string | null;
}

export interface NotificationStatus {
  enabled: boolean;
  configured: boolean;
  worker_running: boolean;
  message: string;
  items: NotificationDelivery[];
}

export interface MediaIncident {
  id: string;
  created_at: string;
  timestamp: number;
  modalities: string[];
  status: string;
  evidence: {
    source: 'image' | 'audio';
    kind: string;
    text: string | null;
    status: string;
  }[];
}

@Injectable({ providedIn: 'root' })
export class ClinicalDataApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/clinical-data';

  imports() {
    return this.http.get<ClinicalImport[]>(`${this.base}/imports`);
  }

  mediaIncidents() {
    return this.http.get<{ items: MediaIncident[]; next_cursor: string | null }>(
      '/api/incidents?limit=100',
    );
  }

  upload(kind: 'vitals' | 'prescriptions', file: File) {
    const data = new FormData();
    data.append('file', file);
    return this.http.post<ClinicalImport>(`${this.base}/${kind}`, data);
  }

  uploadNote(file: File, consentToCloud: boolean) {
    const data = new FormData();
    data.append('file', file);
    data.append('consent_to_cloud', String(consentToCloud));
    return this.http.post<ClinicalImport>(`${this.base}/notes`, data);
  }

  importFhir(patientId: string, kind: FhirKind, authorized: boolean) {
    return this.http.post<ClinicalImport>(`${this.base}/fhir`, {
      patient_id: patientId, kind, authorized,
    });
  }

  notifications() {
    return this.http.get<NotificationStatus>('/api/notifications/status');
  }

  retryNotification(id: string) {
    return this.http.post<{ status: 'pending' }>(`/api/notifications/${encodeURIComponent(id)}/retry`, {});
  }
}
