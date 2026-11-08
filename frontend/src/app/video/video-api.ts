import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';

export type AnalysisMode = 'bed' | 'fisio';
export interface Fence {
  enabled: boolean;
  x: number;
  y: number;
  width: number;
  height: number;
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
  is_sample: number;
  url: string;
}
export interface VideoEvent {
  timestamp: number;
  kind: string;
  severity: 'warning' | 'critical';
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
  frame(id: string, timestamp: number) {
    return this.http.get<FrameMetadata>(`${this.base}/${id}/frame`, { params: { timestamp } });
  }
  events(id: string) {
    return this.http.get<VideoEvent[]>(`${this.base}/${id}/events`);
  }
  fence(id: string, fence: Fence) {
    return this.http.put<ClinicalVideo>(`${this.base}/${id}/fence`, fence);
  }
  report(id: string) {
    return this.http.get<object>(`${this.base}/${id}/report`);
  }
}
