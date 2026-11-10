import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import type { ClinicalAudio, Sentiment } from '../voice/audio-api';

export type AnalysisMode = 'bed' | 'fisio';
export interface Fence {
  enabled: boolean;
  x: number;
  y: number;
  width: number;
  height: number;
}
export interface Thresholds {
  trunk_angle: number;
  knee_angle: number;
}
export interface ClinicalVideo {
  id: string;
  name: string;
  created_at: string;
  mode: AnalysisMode;
  status: 'queued' | 'processing' | 'ready' | 'failed';
  progress: number;
  duration: number;
  fps: number;
  width: number;
  height: number;
  error: string | null;
  fence: Fence;
  thresholds: Thresholds;
  is_sample: number;
  url: string;
  audio: ClinicalAudio | null;
}
export interface VideoEvent {
  timestamp: number;
  kind: string;
  severity: 'warning' | 'critical';
  source?: 'image' | 'audio';
  provisional?: boolean;
}
export interface PersonPose {
  box: [number, number, number, number];
  keypoints: [number, number, number][];
  knee_angle: number | null;
  spine_angle: number | null;
}
export interface FrameMetadata {
  timestamp: number;
  people: PersonPose[];
  fence: Fence;
  events: Pick<VideoEvent, 'kind' | 'severity'>[];
}
export interface MonitorAlert {
  id: string;
  session_id: string;
  video_id: string;
  timestamp: number;
  kind: string;
  source: 'image' | 'audio';
  status: 'provisional' | 'confirmed' | 'retracted';
  created_at: string;
  updated_at: string;
  acknowledged_at: string | null;
  version: number;
}
export interface AlertLogEntry {
  id: number;
  action:
    | 'detected'
    | 'confirmed'
    | 'provisional'
    | 'reopened'
    | 'retracted'
    | 'immediate_care_requested';
  created_at: string;
  payload: MonitorAlert;
}
export interface LiveAudio {
  alerts: MonitorAlert[];
  audio_until: number;
  audio_pending: boolean;
  audio_error: string | null;
  partial_text: string;
  language_pending: boolean;
  events: VideoEvent[];
  transcripts: {
    start: number;
    end: number;
    text: string;
    language: { key_phrases: string[]; sentiment: Sentiment } | null;
    language_pending: boolean;
    language_error: string | null;
  }[];
}
export interface LiveMonitor extends LiveAudio {
  id: string;
  video_id: string;
  start: number;
  closed: boolean;
  target: number;
  analyzed_until: number;
  frame_count: number;
  frame: FrameMetadata | null;
}

@Injectable({ providedIn: 'root' })
export class VideoApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/videos';

  list() {
    return this.http.get<ClinicalVideo[]>(this.base);
  }
  status(id: string) {
    return this.http.get<ClinicalVideo>(`${this.base}/${id}`);
  }
  upload(file: File, mode: AnalysisMode) {
    const data = new FormData();
    data.append('file', file);
    data.append('mode', mode);
    return this.http.post<ClinicalVideo>(this.base, data);
  }
  createMonitor(id: string, timestamp: number) {
    return this.http.post<LiveMonitor>(`${this.base}/${id}/monitor`, { timestamp });
  }
  advanceMonitor(id: string, sessionId: string, timestamp: number) {
    return this.http.post<LiveMonitor>(`${this.base}/${id}/monitor/${sessionId}/advance`, {
      timestamp,
    });
  }
  advanceMonitorAudio(id: string, sessionId: string, timestamp: number, flushAudio: boolean) {
    return this.http.post<LiveAudio>(`${this.base}/${id}/monitor/${sessionId}/audio`, {
      timestamp,
      flush_audio: flushAudio,
    });
  }
  closeMonitor(id: string, sessionId: string) {
    return this.http.delete<void>(`${this.base}/${id}/monitor/${sessionId}`);
  }
  monitorReport(id: string, sessionId: string) {
    return this.http.get<object>(`${this.base}/${id}/monitor/${sessionId}/report`);
  }
  acknowledgeAlerts(id: string, sessionId: string, alertIds: string[]) {
    return this.http.post<MonitorAlert[]>(`${this.base}/${id}/monitor/${sessionId}/acknowledge`, {
      alert_ids: alertIds,
    });
  }
  alertLog(id: string) {
    return this.http.get<AlertLogEntry[]>(`${this.base}/${id}/alert-log`);
  }
  frame(id: string, timestamp: number) {
    return this.http.get<FrameMetadata>(`${this.base}/${id}/frame`, { params: { timestamp } });
  }
  events(id: string) {
    return this.http.get<VideoEvent[]>(`${this.base}/${id}/events`);
  }
  fence(id: string, fence: Fence) {
    return this.http.put<ClinicalVideo>(`${this.base}/${id}/fence`, fence);
  }
  thresholds(id: string, thresholds: Thresholds) {
    return this.http.put<ClinicalVideo>(`${this.base}/${id}/thresholds`, thresholds);
  }
  report(id: string) {
    return this.http.get<object>(`${this.base}/${id}/report`);
  }
}
