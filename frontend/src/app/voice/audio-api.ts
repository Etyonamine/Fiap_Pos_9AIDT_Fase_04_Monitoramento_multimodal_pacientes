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
  end_offset?: number;
  context: string;
}
export interface KeyPhraseMention {
  term: string;
  severity: 'critical' | 'warning';
  negated: boolean;
  key_phrases: string[];
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
    active_window_ratio: number;
    quiet_period_count: number;
    longest_low_energy_seconds: number;
    clipping_ratio: number;
    energy_change_db: number | null;
    experimental_comparison?: {
      status: 'available' | 'insufficient_audio' | 'clipped';
      initial_zero_crossing_rate: number | null;
      final_zero_crossing_rate: number | null;
      difference: number | null;
      notice: string;
    };
    waveform: number[];
    indicators: string[];
    limitation: string;
  } | null;
  result: {
    transcription: {
      provider: string;
      language: string;
      text: string;
      segments: AudioSegment[];
      synthetic?: boolean;
    };
    delivery?: {
      recognized_words: number;
      recognized_speech_seconds: number;
      estimated_words_per_minute: number | null;
      inter_segment_pauses_over_half_second: number;
      longest_inter_segment_pause_seconds: number;
      notice: string;
    };
    critical_terms: CriticalTerm[];
    rules_version: number;
    language?: {
      provider: string;
      key_phrases: string[];
      key_phrase_mentions?: KeyPhraseMention[];
      sentiment: Sentiment;
    };
  } | null;
}
export interface AudioConfiguration {
  configured: boolean;
  message: string;
}

export interface VoiceAcousticFeatures {
  status: 'available' | 'insufficient_speech';
  speech_windows: number;
  median_f0_hz?: number;
  f0_range_hz?: number;
  median_rms_dbfs?: number;
  median_zero_crossing_rate?: number;
  notice: string;
}

export interface VoiceAcousticComparison {
  status: 'available' | 'insufficient_speech';
  current: VoiceAcousticFeatures;
  reference: VoiceAcousticFeatures;
  differences?: {
    median_f0_percent: number;
    f0_range_percent: number;
    median_rms_db: number;
    zero_crossing_rate_percent: number;
  };
  changed_features: string[];
  notice: string;
  review?: {
    status: 'insufficient_acoustic_data' | 'combined_evidence' | 'acoustic_change_only'
      | 'reported_mention_only' | 'no_flags';
    changed_features: string[];
    reported_mentions: { term: string; severity: 'critical' | 'warning' }[];
    notice: string;
  };
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
  compare(id: string, referenceId: string) {
    return this.http.post<VoiceAcousticComparison>(
      `${this.base}/${encodeURIComponent(id)}/compare/${encodeURIComponent(referenceId)}`, {},
    );
  }
  delete(id: string) {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}
