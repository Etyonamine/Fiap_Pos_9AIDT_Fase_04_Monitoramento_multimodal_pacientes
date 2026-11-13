import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import type { ClinicalAudio, Sentiment } from '../voice/audio-api';

export type AnalysisMode = 'bed' | 'fisio';
export type Posture = 'standing' | 'sitting' | 'lying';
export type PostureChoice = Posture | 'hybrid';
export interface PostureInterval {
  start: number;
  end: number;
  posture: Posture;
}
export interface PostureConfig {
  type: PostureChoice | 'unclassified';
  intervals: PostureInterval[];
}
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
  posture_config: PostureConfig | null;
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
  fence_subject?: boolean;
  unavailable_metrics?: ('knee_angle' | 'spine_angle')[];
}
export interface FrameMetadata {
  timestamp: number;
  people: PersonPose[];
  fence: Fence;
  events: Pick<VideoEvent, 'kind' | 'severity'>[];
  posture?: Posture | null;
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
export interface CameraMonitorState {
  id: string;
  closed: boolean;
  frame: FrameMetadata | null;
  alerts: MonitorAlert[];
  events: VideoEvent[];
  frame_count: number;
  elapsed: number;
  recording_id: string | null;
  audio_error: string | null;
  partial_text: string;
  transcripts: LiveAudio['transcripts'];
}

@Injectable({ providedIn: 'root' })
export class VideoApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/videos';
  cameraFence() {
    return this.http.get<{ fence: Fence | null }>('/api/camera/fence');
  }
  saveCameraFence(fence: Fence) {
    return this.http.put<{ fence: Fence }>('/api/camera/fence', fence);
  }
  createCameraMonitor(fence: Fence, record: boolean) {
    return this.http.post<CameraMonitorState>('/api/camera/monitor', { fence, record });
  }
  cameraFrame(id: string, file: Blob, timestamp: number) {
    const data = new FormData();
    data.append('file', file, 'frame.jpg');
    data.append('timestamp', String(timestamp));
    return this.http.post<CameraMonitorState>(`/api/camera/monitor/${id}/frame`, data);
  }
  cameraAudio(id: string, file: Blob, timestamp: number) {
    const data = new FormData();
    data.append('file', file, 'audio.wav');
    data.append('timestamp', String(timestamp));
    return this.http.post<CameraMonitorState>(`/api/camera/monitor/${id}/audio`, data);
  }
  closeCameraMonitor(id: string) {
    return this.http.delete<CameraMonitorState>(`/api/camera/monitor/${id}`);
  }
  acknowledgeCameraAlerts(id: string, alertIds: string[]) {
    return this.http.post<MonitorAlert[]>(`/api/camera/monitor/${id}/acknowledge`, {
      alert_ids: alertIds,
    });
  }
  cameraAlertLog() {
    return this.http.get<AlertLogEntry[]>('/api/camera/alert-log');
  }

  list() {
    return this.http.get<ClinicalVideo[]>(this.base);
  }
  status(id: string) {
    return this.http.get<ClinicalVideo>(`${this.base}/${id}`);
  }
  upload(file: File, mode: AnalysisMode, posture?: PostureConfig) {
    const data = new FormData();
    data.append('file', file);
    data.append('mode', mode);
    if (posture) data.append('posture', JSON.stringify(posture));
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
