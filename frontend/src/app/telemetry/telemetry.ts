import { ChangeDetectionStrategy, Component, computed, DestroyRef, inject, signal } from '@angular/core';
import { DatePipe, NgTemplateOutlet } from '@angular/common';
import { RouterLink } from '@angular/router';
import { VideoWorkspace } from '../video/video-workspace';
import { CameraMonitor } from '../video/camera-monitor';

type Scenario = 'stable' | 'vitals' | 'sudden-deterioration' | 'prescription' | 'combined';

interface VitalSample {
  step: number;
  recordedAt: number;
  heartRate: number;
  systolic: number;
  diastolic: number;
  oxygen: number;
}

interface SimulationAlert {
  step: number;
  message: string;
}

type VitalMetric = 'heartRate' | 'systolic' | 'diastolic' | 'oxygen';

function trendPoints(samples: VitalSample[], metric: VitalMetric, maximum: number): string {
  return samples.map((sample, index) =>
    `${4 + (index * 192) / 7},${44 - (sample[metric] / maximum) * 40}`,
  ).join(' ');
}

const BASELINE: Omit<VitalSample, 'recordedAt'> = {
  step: 0,
  heartRate: 78,
  systolic: 120,
  diastolic: 80,
  oxygen: 98,
};
const SAMPLE_INTERVAL_SECONDS = 5;
const SUDDEN_DETERIORATION_STEP = 6;
const SUDDEN_DETERIORATION_END_STEP = 8;

@Component({
  selector: 'app-telemetry',
  imports: [DatePipe, NgTemplateOutlet, RouterLink, VideoWorkspace, CameraMonitor],
  templateUrl: './telemetry.html',
  styleUrl: './telemetry.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Telemetry {
  readonly source = signal<'recordings' | 'camera'>('recordings');
  readonly scenario = signal<Scenario>('stable');
  readonly running = signal(false);
  readonly samples = signal<VitalSample[]>([{ ...BASELINE, recordedAt: Date.now() }]);
  readonly alerts = signal<SimulationAlert[]>([]);
  readonly current = computed(() => this.samples()[this.samples().length - 1]);
  readonly elapsedSeconds = computed(() => this.current().step * SAMPLE_INTERVAL_SECONDS);
  readonly completed = computed(
    () => this.scenario() === 'sudden-deterioration' &&
      this.current().step >= SUDDEN_DETERIORATION_END_STEP,
  );
  readonly trends = computed(() => {
    const samples = this.samples();
    return {
      heartRate: trendPoints(samples, 'heartRate', 200),
      systolic: trendPoints(samples, 'systolic', 220),
      diastolic: trendPoints(samples, 'diastolic', 220),
      oxygen: trendPoints(samples, 'oxygen', 100),
    };
  });
  readonly doseChanged = computed(
    () => this.current().step >= 2 && ['prescription', 'combined'].includes(this.scenario()),
  );
  private interval: ReturnType<typeof setInterval> | null = null;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.pause());
  }

  onSourceKeydown(event: KeyboardEvent): void {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const source = event.key === 'Home' ? 'recordings' : event.key === 'End' ? 'camera'
      : this.source() === 'recordings' ? 'camera' : 'recordings';
    this.source.set(source);
    if (event.currentTarget instanceof HTMLElement) {
      event.currentTarget.querySelector<HTMLButtonElement>(`#${source}-tab`)?.focus();
    }
  }

  changeScenario(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    if (value !== 'stable' && value !== 'vitals' && value !== 'sudden-deterioration' &&
        value !== 'prescription' && value !== 'combined') {
      throw new Error(`Cenário de simulação inválido: ${value}`);
    }
    this.scenario.set(value);
    this.reset();
  }

  start(): void {
    if (this.interval !== null || this.completed()) return;
    this.running.set(true);
    this.interval = setInterval(() => this.advance(), SAMPLE_INTERVAL_SECONDS * 1000);
  }

  pause(): void {
    if (this.interval !== null) clearInterval(this.interval);
    this.interval = null;
    this.running.set(false);
  }

  reset(): void {
    this.pause();
    this.samples.set([{ ...BASELINE, recordedAt: Date.now() }]);
    this.alerts.set([]);
  }

  private advance(): void {
    const step = this.current().step + 1;
    const vitalAnomaly =
      (step >= 2 && ['vitals', 'combined'].includes(this.scenario())) ||
      (step >= SUDDEN_DETERIORATION_STEP && this.scenario() === 'sudden-deterioration');
    const next: VitalSample = vitalAnomaly
      ? { step, recordedAt: Date.now(), heartRate: 128, systolic: 185, diastolic: 112, oxygen: 88 }
      : { step, recordedAt: Date.now(), heartRate: step % 2 ? 80 : 78, systolic: 120, diastolic: 80, oxygen: 98 };
    const previous = this.current();
    const messages: string[] = [];
    if (next.heartRate > 120 && previous.heartRate <= 120) {
      messages.push('Frequência cardíaca acima do limite demonstrativo de 120 bpm.');
    }
    if ((next.systolic > 180 || next.diastolic > 110) &&
        previous.systolic <= 180 && previous.diastolic <= 110) {
      messages.push('Pressão arterial acima do limite demonstrativo de 180/110 mmHg.');
    }
    if (next.oxygen < 90 && previous.oxygen >= 90) {
      messages.push('Oxigenação abaixo do limite demonstrativo de 90%.');
    }
    if (step === 2 && ['prescription', 'combined'].includes(this.scenario())) {
      messages.push('Prescrição fictícia: dose do Medicamento A triplicou de 10 para 30 mg.');
    }
    this.samples.update((samples) => [...samples, next].slice(-8));
    this.alerts.update((alerts) => [...alerts, ...messages.map((message) => ({ step, message }))]);
    if (this.completed()) this.pause();
  }
}
