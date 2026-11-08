import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';

export type AudioStatus = 'importing' | 'uploaded' | 'queued' | 'analyzing' | 'ready' | 'failed';
export type SentimentLabel = 'positive' | 'neutral' | 'negative' | 'mixed';
export interface AudioSegment {
  text: string;
  offset: number;
  duration: number;
  confidence: number | null;
}
export interface CriticalTerm {
  term: string;
  severity: 'critical' | 'warning';
  negated: boolean;
  offset: number;
  context: string;
}
export interface Sentiment {
  label: SentimentLabel;
  scores: { positive: number; neutral: number; negative: number };
  chunks: { text: string; label: SentimentLabel; scores: Sentiment['scores'] }[];
  aggregation: string;
}
export interface ClinicalAudio {
  id: string;
  name: string;
  status: AudioStatus;
  created_at: string;
  duration: number;
  error: string | null;
  url: string | null;
  acoustic: {
    duration: number;
    rms_energy: number;
    low_energy_ratio: number;
    longest_low_energy_seconds: number;
    clipping_ratio: number;
    energy_change_db: number | null;
    waveform: number[];
    indicators: string[];
    limitation: string;
  } | null;
  result: {
    transcription: { provider: string; language: string; text: string; segments: AudioSegment[] };
    critical_terms: CriticalTerm[];
    rules_version: number;
    language?: { provider: string; key_phrases: string[]; sentiment: Sentiment };
  } | null;
}
export interface AudioConfiguration {
  configured: boolean;
  message: string;
}

@Injectable({ providedIn: 'root' })
export class AudioApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/audios';

  list() {
    return this.http.get<ClinicalAudio[]>(this.base);
  }
  configuration() {
    return this.http.get<AudioConfiguration>(`${this.base}/configuration`);
  }
  status(id: string) {
    return this.http.get<ClinicalAudio>(`${this.base}/${id}`);
  }
  upload(file: File) {
    const data = new FormData();
    data.append('file', file);
    return this.http.post<ClinicalAudio>(this.base, data);
  }
  analyze(id: string) {
    return this.http.post<ClinicalAudio>(`${this.base}/${id}/analyze`, {});
  }
  delete(id: string) {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}
