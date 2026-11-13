import { DATE_PIPE_DEFAULT_OPTIONS } from '@angular/common';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { VideoWorkspace } from './video-workspace';
import { ClinicalVideo, LiveAudio, LiveMonitor, MonitorAlert } from './video-api';

const source: ClinicalVideo = {
  id: 'bed',
  name: 'bed.mp4',
  created_at: '2025-01-02T03:04:00.000Z',
  mode: 'bed',
  status: 'ready',
  progress: 1,
  duration: 1,
  fps: 25,
  width: 100,
  height: 100,
  error: null,
  is_sample: 1,
  url: '/api/videos/bed/media',
  audio: null,
  thresholds: { trunk_angle: 35, knee_angle: 60 },
  posture_config: null,
  fence: { enabled: true, x: 0.1, y: 0.1, width: 0.8, height: 0.9 },
};
const soundState: LiveAudio = {
  alerts: [],
  audio_until: 0,
  audio_pending: false,
  audio_error: null,
  partial_text: '',
  language_pending: false,
  events: [],
  transcripts: [],
};
const live: LiveMonitor = {
  ...soundState,
  id: 'session',
  video_id: source.id,
  start: 0,
  closed: false,
  target: 0,
  analyzed_until: 0,
  frame_count: 0,
  frame: null,
};
const recordedAlert: MonitorAlert = {
  id: 'alert-1',
  session_id: 'session',
  video_id: 'bed',
  timestamp: 0.1,
  kind: 'Fala: socorro',
  source: 'audio',
  status: 'provisional',
  created_at: '2026-11-10T00:00:00.000+00:00',
  updated_at: '2026-11-10T00:00:00.000+00:00',
  acknowledged_at: null,
  version: 1,
};

describe('Video workspace', () => {
  let http: HttpTestingController;
  let originalMediaDevices: PropertyDescriptor | undefined;

  beforeEach(() => {
    originalMediaDevices = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');
    TestBed.configureTestingModule({
      imports: [VideoWorkspace],
      providers: [
        provideRouter([]), provideHttpClient(), provideHttpClientTesting(),
        { provide: DATE_PIPE_DEFAULT_OPTIONS, useValue: { timezone: 'UTC' } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    Object.defineProperty(HTMLVideoElement.prototype, 'requestVideoFrameCallback', {
      configurable: true,
      value: vi.fn(() => 1),
    });
    Object.defineProperty(HTMLVideoElement.prototype, 'cancelVideoFrameCallback', {
      configurable: true,
      value: vi.fn(),
    });
  });
  afterEach(() => {
    TestBed.resetTestingModule();
    http.verify({ ignoreCancelled: true });
    if (originalMediaDevices)
      Object.defineProperty(navigator, 'mediaDevices', originalMediaDevices);
    else Reflect.deleteProperty(navigator, 'mediaDevices');
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  function setup() {
    const fixture = TestBed.createComponent(VideoWorkspace);
    fixture.componentRef.setInput('mode', 'bed');
    http.expectOne('/api/videos').flush([source]);
    fixture.detectChanges();
    return fixture;
  }

  it('keeps the recording fence visible without frame metadata and previews edits immediately', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    for (const mode of ['bed', 'fisio'] as const) {
      fixture.componentRef.setInput('mode', mode);
      component.selected.set({ ...source, mode, width: 1920, height: 1080 });
      fixture.detectChanges();
      const fence: SVGElement = fixture.nativeElement.querySelector(
        '.video-surface:not(.camera-surface) .fence-overlay',
      );
      expect(component.metadata()).toBeNull();
      expect(fence.getAttribute('viewBox')).toBe('0 0 1920 1080');
      expect(fence.getAttribute('aria-label')).toBe('Cerca virtual ativa');
      expect(fence.querySelector('rect')?.getAttribute('x')).toBe('10%');
      component.editingFence.set(true);
      component.fenceDraft.set({ ...source.fence, x: 0.2, width: 0.6 });
      fixture.detectChanges();
      expect(fence.querySelector('rect')?.getAttribute('x')).toBe('20%');
      expect(fence.querySelector('rect')?.getAttribute('width')).toBe('60%');
      expect(fence.getAttribute('aria-label')).toBe('Prévia do ajuste da cerca virtual');
      component.editingFence.set(false);
      component.selected.set({ ...source, mode, fence: { ...source.fence, enabled: false } });
      fixture.detectChanges();
      expect(fence.classList.contains('inactive')).toBe(true);
      expect(fence.getAttribute('aria-label')).toContain('desativada');
      component.metadata.set({ timestamp: 0, fence: source.fence, people: [], events: [] });
      fixture.detectChanges();
      expect(fence.classList.contains('inactive')).toBe(true);
      component.metadata.set(null);
    }
  });

  it('shows an illustrative camera fence matching the stream dimensions without analysis', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    const player = component.cameraPlayer()!.nativeElement;
    Object.defineProperty(player, 'videoWidth', { configurable: true, value: 1280 });
    Object.defineProperty(player, 'videoHeight', { configurable: true, value: 720 });
    component.cameraPreview.set(true);
    player.dispatchEvent(new Event('loadedmetadata'));
    fixture.detectChanges();
    const surface: HTMLElement = fixture.nativeElement.querySelector('.camera-surface');
    expect(surface.hidden).toBe(false);
    expect(surface.querySelector('svg')?.getAttribute('viewBox')).toBe('0 0 1280 720');
    expect(surface.querySelector('rect')?.getAttribute('height')).toBe('90%');
    expect(surface.querySelector('svg')?.getAttribute('aria-label')).toContain('sem análise');
    expect(fixture.nativeElement.textContent).toContain('não detecta saídas nem gera alertas');
    expect(component.monitor()).toBeNull();
    Object.defineProperty(player, 'videoWidth', { configurable: true, value: 640 });
    Object.defineProperty(player, 'videoHeight', { configurable: true, value: 480 });
    player.dispatchEvent(new Event('resize'));
    fixture.detectChanges();
    expect(surface.querySelector('svg')?.getAttribute('viewBox')).toBe('0 0 640 480');
  });

  it('draws a bed fence in image coordinates despite letterboxing and saves only on confirmation', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set({ ...source, width: 200, height: 100 });
    fixture.detectChanges();
    component.editFence();
    fixture.detectChanges();
    const svg: SVGSVGElement = fixture.nativeElement.querySelector(
      '.video-surface:not(.camera-surface) .fence-overlay',
    );
    vi.spyOn(svg, 'getBoundingClientRect').mockReturnValue(new DOMRect(100, 200, 400, 400));
    Object.defineProperties(svg, {
      setPointerCapture: { value: vi.fn(), configurable: true },
      hasPointerCapture: { value: () => true, configurable: true },
      releasePointerCapture: { value: vi.fn(), configurable: true },
    });
    const pointer = (type: string, x: number, y: number, pointerId = 1) => {
      const event = new Event(type, { bubbles: true, cancelable: true });
      Object.defineProperties(event, {
        clientX: { value: x }, clientY: { value: y },
        pointerId: { value: pointerId }, button: { value: 0 },
      });
      svg.dispatchEvent(event);
      fixture.detectChanges();
    };
    pointer('pointerdown', 150, 220);
    expect(component.drawingFence()).toBe(false);
    expect(component.fenceNotice()).toContain('barras');
    pointer('pointerdown', 420, 460);
    pointer('pointermove', 180, 340, 2);
    expect(component.fenceDraft()).toEqual(source.fence);
    pointer('pointermove', 180, 340);
    expect(component.fenceDraft()).toEqual({
      enabled: true, x: 0.2, y: 0.2, width: 0.6000000000000001, height: 0.6000000000000001,
    });
    component.saveFence();
    http.expectNone('/api/videos/bed/fence');
    pointer('pointerup', 180, 340);
    expect(component.drawingFence()).toBe(false);
    expect(component.selected()?.fence).toEqual(source.fence);
    component.saveFence();
    const request = http.expectOne('/api/videos/bed/fence');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual(component.fenceDraft());
    request.flush({ ...source, fence: request.request.body });
    fixture.detectChanges();
    expect(component.editingFence()).toBe(false);
    expect(component.fenceNotice()).toContain('desde antes da saída');
    expect(component.sources().find(video => video.id === source.id)?.fence).toEqual(
      request.request.body,
    );
  });

  it('blocks native playback and monitor creation while the displayed fence is only a draft', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    fixture.detectChanges();
    component.editFence();
    component.fenceDraft.set({ enabled: true, x: .4, y: .2, width: .5, height: .7 });
    fixture.detectChanges();
    const player = component.player()!.nativeElement;
    expect(player.controls).toBe(false);
    expect(fixture.nativeElement.textContent).toContain('PRÉVIA NÃO APLICADA');
    expect(fixture.nativeElement.querySelector('.fence-overlay.draft')).not.toBeNull();
    vi.spyOn(player, 'paused', 'get').mockReturnValue(false);
    player.dispatchEvent(new Event('play'));
    component.onLoaded();
    fixture.detectChanges();
    expect(player.pause).toHaveBeenCalled();
    http.expectNone('/api/videos/bed/monitor');
    expect(component.monitor()).toBeNull();
    expect(component.fenceNotice()).toContain('Reprodução bloqueada');
    component.cancelFenceEditing();
    fixture.detectChanges();
    expect(player.controls).toBe(true);
    expect(component.displayedFence()).toEqual(source.fence);
    expect(fixture.nativeElement.querySelector('.fence-overlay.draft')).toBeNull();
  });

  it('keeps playback blocked on a failed save and preserves the draft for retry', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    fixture.detectChanges();
    component.editFence();
    const draft = { enabled: true, x: .4, y: .2, width: .5, height: .7 };
    component.fenceDraft.set(draft);
    component.saveFence();
    http.expectOne('/api/videos/bed/fence').flush({ detail: 'Falha ao salvar cerca' },
      { status: 500, statusText: 'Internal Server Error' });
    fixture.detectChanges();
    expect(component.error()).toBe('Falha ao salvar cerca');
    expect(component.fencePlaybackBlocked()).toBe(true);
    expect(component.fenceDraft()).toEqual(draft);
    expect(component.selected()?.fence).toEqual(source.fence);
    component.saveFence();
    http.expectOne('/api/videos/bed/fence').flush({ ...source, fence: draft });
    fixture.detectChanges();
    expect(component.fencePlaybackBlocked()).toBe(false);
    expect(component.selected()?.fence).toEqual(draft);
  });

  it('preserves the previous fence when a drawing is too small or cancelled and clamps to the image', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    fixture.detectChanges();
    component.editFence();
    fixture.detectChanges();
    const svg: SVGSVGElement = fixture.nativeElement.querySelector(
      '.video-surface:not(.camera-surface) .fence-overlay',
    );
    vi.spyOn(svg, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 100, 100));
    Object.defineProperties(svg, {
      setPointerCapture: { value: vi.fn(), configurable: true },
      hasPointerCapture: { value: () => false, configurable: true },
    });
    const pointer = (type: string, x: number, y: number) => {
      const event = new Event(type, { bubbles: true });
      Object.defineProperties(event, {
        clientX: { value: x }, clientY: { value: y },
        pointerId: { value: 1 }, button: { value: 0 },
      });
      svg.dispatchEvent(event);
      fixture.detectChanges();
    };
    pointer('pointerdown', 20, 20);
    pointer('pointerup', 20.1, 20.1);
    expect(component.fenceDraft()).toEqual(source.fence);
    expect(component.fenceNotice()).toContain('pelo menos 1%');
    pointer('pointerdown', 20, 20);
    pointer('pointermove', 150, 150);
    expect(component.fenceDraft()).toEqual({
      enabled: true, x: 0.2, y: 0.2, width: 0.8, height: 0.8,
    });
    pointer('pointercancel', 150, 150);
    expect(component.fenceDraft()).toEqual(source.fence);
    expect(component.fenceNotice()).toContain('cancelada');
  });

  it('records immediate-care intent once and preserves it when older poll results arrive', () => {
    vi.useFakeTimers();
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    fixture.detectChanges();
    vi.spyOn(component.player()!.nativeElement, 'paused', 'get').mockReturnValue(false);
    component.onPlay();
    http.expectOne('/api/videos/bed/monitor').flush(live);
    component.sync(0.6);
    vi.advanceTimersByTime(0);
    const image = http.expectOne('/api/videos/bed/monitor/session/advance');
    http.expectOne('/api/videos/bed/monitor/session/audio').flush({
      ...soundState,
      alerts: [recordedAlert],
      events: [
        {
          timestamp: 0.1,
          kind: 'Fala: socorro',
          severity: 'critical',
          source: 'audio',
          provisional: true,
        },
      ],
    });
    fixture.detectChanges();
    const button: HTMLButtonElement = fixture.nativeElement.querySelector('.attend-now');
    expect(button.textContent).toContain('Ir ao atendimento');
    button.click();
    component.acknowledgeAttendance();
    const request = http.expectOne('/api/videos/bed/monitor/session/acknowledge');
    expect(request.request.body).toEqual({ alert_ids: ['alert-1'] });
    expect(component.acknowledging()).toBe(true);
    const acknowledged = {
      ...recordedAlert,
      acknowledged_at: '2026-11-10T00:01:00.000+00:00',
      version: 2,
    };
    request.flush([acknowledged]);
    http.expectOne('/api/videos/bed/alert-log').flush([{
      id: 2, action: 'immediate_care_requested',
      created_at: acknowledged.acknowledged_at, payload: acknowledged,
    }]);
    image.flush({ ...live, alerts: [recordedAlert] });
    fixture.detectChanges();
    expect(component.alertRecords()[0].acknowledged_at).toBe(acknowledged.acknowledged_at);
    expect(button.textContent).toContain('Ida ao atendimento registrada');
    expect(button.disabled).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('Ida ao atendimento registrada em');
    expect(fixture.nativeElement.textContent).toContain('10/11/2026 00:01:00');
    expect(fixture.nativeElement.querySelector('.attendance-registered')?.getAttribute('role')).toBe('status');
    expect(fixture.nativeElement.querySelector('.alert-history')?.textContent).toContain('Ida ao atendimento registrada pelo botão');
    component.onSeeking();
    http.expectOne('/api/videos/bed/monitor/session').flush(null);
  });

  it('shows acknowledgement failures without claiming that care was registered', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    component.monitor.set(live);
    component.currentTime.set(0.6);
    component.events.set([
      {
        timestamp: 0.1,
        kind: 'Fala: socorro',
        severity: 'critical',
        source: 'audio',
      },
    ]);
    component.alertRecords.set([recordedAlert]);
    component.acknowledgeAttendance();
    http
      .expectOne('/api/videos/bed/monitor/session/acknowledge')
      .flush({ detail: 'Não foi possível registrar.' }, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(component.acknowledging()).toBe(false);
    expect(component.pendingAttendance()).toHaveLength(1);
    expect(component.acknowledgedAttendance()).toEqual([]);
    expect(fixture.nativeElement.textContent).toContain('Não foi possível registrar.');
    component.monitor.set(null);
  });

  it('hides the registered panel after five seconds without removing records and restores it for new alerts', () => {
    vi.useFakeTimers();
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    component.monitor.set(live);
    component.currentTime.set(1);
    const event = {
      timestamp: .1, kind: 'Fala: socorro',
      severity: 'critical' as const, source: 'audio' as const,
    };
    component.events.set([event]);
    component.alertRecords.set([{
      ...recordedAlert, acknowledged_at: '2026-11-10T00:01:00Z', version: 2,
    }]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-registered')).not.toBeNull();
    vi.advanceTimersByTime(4999);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-registered')).not.toBeNull();
    vi.advanceTimersByTime(1);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')).toBeNull();
    expect(component.acknowledgedAttendance()).toHaveLength(1);
    component.events.set([event, { ...event, timestamp: .5, kind: 'Saída da cerca virtual', source: 'image' }]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')?.getAttribute('role')).toBe('alert');
    vi.advanceTimersByTime(5000);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')).not.toBeNull();
    component.monitor.set(null);
    fixture.detectChanges();
  });

  it('loads persisted detection and care logs when requested', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    component.loadAlertHistory();
    http.expectOne('/api/videos/bed/alert-log').flush([
      {
        id: 2,
        action: 'immediate_care_requested',
        created_at: '2026-11-10T00:01:00.000+00:00',
        payload: recordedAlert,
      },
      {
        id: 1,
        action: 'detected',
        created_at: recordedAlert.created_at,
        payload: recordedAlert,
      },
    ]);
    fixture.detectChanges();
    const history: HTMLElement = fixture.nativeElement.querySelector('.alert-history');
    expect(history.textContent).toContain('Ida ao atendimento registrada pelo botão');
    expect(history.textContent).toContain('Alerta disparado');
    expect(history.textContent).toContain('Fala: socorro');
  });

  it('shows metrics and confidence status for the tracked person, not the first detection', () => {
    const fixture = setup();
    fixture.componentRef.setInput('mode', 'fisio');
    const component = fixture.componentInstance;
    component.selected.set({ ...source, mode: 'fisio' });
    component.metadata.set({
      timestamp: 0,
      fence: source.fence,
      events: [],
      people: [
        {
          box: [0.1, 0.1, 0.2, 0.3],
          keypoints: [],
          knee_angle: 40,
          spine_angle: 10,
          fence_subject: false,
        },
        {
          box: [0.3, 0.2, 0.4, 0.5],
          keypoints: [],
          knee_angle: null,
          spine_angle: 12,
          fence_subject: true,
          unavailable_metrics: ['knee_angle'],
        },
      ],
    });

    fixture.detectChanges();

    expect(component.telemetry()?.spine_angle).toBe(12);
    expect(fixture.nativeElement.textContent).toContain('Análise inconclusiva');
    expect(fixture.nativeElement.textContent).toContain('ângulo do joelho');
    expect(fixture.nativeElement.textContent).toContain('Pessoa analisada');
  });

  it('identifies unmarked hybrid gaps as inconclusive and explains lying posture', () => {
    const fixture = setup();
    fixture.componentRef.setInput('mode', 'fisio');
    const component = fixture.componentInstance;
    component.selected.set({
      ...source,
      mode: 'fisio',
      posture_config: {
        type: 'hybrid',
        intervals: [{ start: 0, end: 0.5, posture: 'lying' }],
      },
    });
    const frame = {
      timestamp: 0,
      fence: source.fence,
      events: [],
      people: [{
        box: [0.1, 0.1, 0.5, 0.5] as [number, number, number, number],
        keypoints: [],
        knee_angle: 80,
        spine_angle: 85,
        fence_subject: true,
      }],
    };
    component.metadata.set({ ...frame, posture: null });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('este trecho não possui postura informada');
    component.metadata.set({ ...frame, posture: 'lying' });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('não avalia a coluna lombar');
    expect(fixture.nativeElement.textContent).toContain('Intervalos de postura informados');
  });

  it('repeats the beep until care is persisted, survives failures and restarts for new alerts', async () => {
    vi.useFakeTimers();
    const oscillator = {
      frequency: { value: 0 },
      type: 'sine',
      onended: null,
      connect: vi.fn(),
      disconnect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
    };
    const gain = {
      gain: {
        setValueAtTime: vi.fn(),
        linearRampToValueAtTime: vi.fn(),
        exponentialRampToValueAtTime: vi.fn(),
      },
      connect: vi.fn(),
      disconnect: vi.fn(),
    };
    const context = {
      state: 'running',
      currentTime: 0,
      destination: {},
      resume: vi.fn().mockResolvedValue(undefined),
      close: vi.fn().mockResolvedValue(undefined),
      createOscillator: vi.fn(() => oscillator),
      createGain: vi.fn(() => gain),
    };
    vi.stubGlobal(
      'AudioContext',
      class {
        constructor() {
          return context;
        }
      },
    );
    const fixture = setup();
    const component = fixture.componentInstance;
    await component.enableAlertSound();
    component.selected.set(source);
    component.monitor.set(live);
    component.currentTime.set(0.6);
    const trigger = {
      timestamp: 0.1,
      kind: 'Fala: socorro',
      severity: 'critical' as const,
      source: 'audio' as const,
      provisional: true,
    };
    component.events.set([trigger]);
    component.alertRecords.set([recordedAlert]);
    fixture.detectChanges();
    expect(oscillator.start).toHaveBeenCalledTimes(1);
    expect(oscillator.frequency.value).toBe(880);
    component.events.set([{ ...trigger, provisional: false }]);
    fixture.detectChanges();
    expect(oscillator.start).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(3000);
    expect(oscillator.start).toHaveBeenCalledTimes(4);
    component.acknowledgeAttendance();
    const failed = http.expectOne('/api/videos/bed/monitor/session/acknowledge');
    vi.advanceTimersByTime(1000);
    expect(oscillator.start).toHaveBeenCalledTimes(5);
    failed.flush({ detail: 'Falha ao registrar' }, { status: 500, statusText: 'Error' });
    vi.advanceTimersByTime(1000);
    expect(oscillator.start).toHaveBeenCalledTimes(6);
    component.acknowledgeAttendance();
    http.expectOne('/api/videos/bed/monitor/session/acknowledge').flush([
      {
        ...recordedAlert,
        acknowledged_at: '2026-11-10T00:01:00Z',
        version: 2,
      },
    ]);
    http.expectOne('/api/videos/bed/alert-log').flush([]);
    fixture.detectChanges();
    vi.advanceTimersByTime(3000);
    expect(oscillator.start).toHaveBeenCalledTimes(6);
    component.events.set([
      { ...trigger, provisional: false },
      {
        timestamp: 0.2,
        kind: 'Fala: tontura',
        severity: 'warning',
      },
    ]);
    fixture.detectChanges();
    expect(oscillator.start).toHaveBeenCalledTimes(6);
    component.events.set([trigger, { ...trigger, timestamp: 0.4, kind: 'Fala: me ajuda' }]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-registered')).toBeNull();
    expect(fixture.nativeElement.querySelector('.attendance-alert')?.getAttribute('role')).toBe('alert');
    expect(oscillator.start).toHaveBeenCalledTimes(7);
    vi.advanceTimersByTime(2000);
    expect(oscillator.start).toHaveBeenCalledTimes(9);
    component.events.set([{ timestamp: 0.2, kind: 'Fala: tontura', severity: 'warning' }]);
    fixture.detectChanges();
    vi.advanceTimersByTime(2000);
    expect(oscillator.start).toHaveBeenCalledTimes(9);
    component.events.set([trigger]);
    component.alertRecords.set([]);
    fixture.detectChanges();
    expect(oscillator.start).toHaveBeenCalledTimes(10);
    component.monitor.set(null);
    fixture.detectChanges();
    vi.advanceTimersByTime(2000);
    expect(oscillator.start).toHaveBeenCalledTimes(10);
    component.monitor.set(live);
    fixture.detectChanges();
    expect(oscillator.start).toHaveBeenCalledTimes(11);
    fixture.destroy();
    http.expectOne('/api/videos/bed/monitor/session').flush(null);
    vi.advanceTimersByTime(3000);
    expect(oscillator.start).toHaveBeenCalledTimes(11);
  });

  it('explicitly reports browser sound failures without hiding visual alerts', async () => {
    vi.stubGlobal(
      'AudioContext',
      class {
        constructor() {
          throw new Error('blocked');
        }
      },
    );
    const component = setup().componentInstance;
    await component.enableAlertSound();
    expect(component.soundError()).toContain('Não foi possível ativar o bip');
  });

  it('renders bed monitoring and native scrubbing controls without a mode selector', () => {
    const fixture = setup();
    fixture.componentInstance.selected.set(source);
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector<HTMLVideoElement>('video[controls]')?.controls).toBe(true);
    expect(element.textContent).toContain('Monitoramento de leitos');
    expect(element.querySelector('.mode-navigation')).toBeNull();
    expect(element.textContent).not.toContain('Enviar vídeo de fisioterapia');
    expect(element.textContent).toContain('Ajustar cerca virtual');
  });

  it('clarifies that an empty event log means no alert was detected', () => {
    const fixture = setup();
    fixture.componentRef.setInput('mode', 'fisio');
    fixture.componentInstance.selected.set({ ...source, mode: 'fisio' });
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.event-log').textContent).toContain(
      'Vídeo analisado; nenhum evento de alerta foi detectado.',
    );
  });

  it('shows only the five newest sources with their analysis date and time', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.videos.set(
      Array.from({ length: 7 }, (_, index) => ({
        ...source,
        id: `video-${index}`,
        name: `video-${index}.mp4`,
        created_at: `2025-01-0${index + 1}T03:04:00.000Z`,
      })),
    );
    fixture.detectChanges();

    const files = fixture.nativeElement.querySelectorAll('.file');
    expect(files).toHaveLength(5);
    expect(files[0].textContent).toContain('video-6.mp4');
    expect(fixture.nativeElement.textContent).not.toContain('video-1.mp4');
    expect(fixture.nativeElement.textContent).not.toContain('video-0.mp4');
    expect(files[0].querySelector('time')?.getAttribute('datetime')).toBe(
      '2025-01-07T03:04:00.000Z',
    );
    expect(files[0].textContent).toContain('07/01/2025 03:04');
  });

  it('requests the current timestamp and cancels stale scrubbing metadata', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set({ ...source, mode: 'fisio' });
    fixture.detectChanges();
    const player = component.player()!.nativeElement;
    player.currentTime = 0.08;
    component.sync();
    const old = http.expectOne('/api/videos/bed/frame?timestamp=0.08');
    player.currentTime = 0.04;
    component.onSeeking();
    expect(old.cancelled).toBe(true);
    const request = http.expectOne('/api/videos/bed/frame?timestamp=0.04');
    expect(component.metadata()).toBeNull();
    request.flush({ timestamp: 0.04, people: [], fence: source.fence, events: [] });
    expect(component.metadata()?.timestamp).toBe(0.04);
    expect(component.currentTime()).toBe(0.04);
  });

  it('tracks the last event at or before the player time, including backwards seeks', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.events.set([
      { timestamp: 0.1, kind: 'A', severity: 'warning' },
      { timestamp: 0.5, kind: 'B', severity: 'critical' },
    ]);
    component.currentTime.set(0.8);
    expect(component.activeEvent()).toBe(1);
    component.currentTime.set(0.3);
    expect(component.activeEvent()).toBe(0);
    component.currentTime.set(0);
    expect(component.activeEvent()).toBe(-1);
  });

  it('shows API errors instead of fabricated demonstration data', () => {
    const fixture = TestBed.createComponent(VideoWorkspace);
    fixture.componentRef.setInput('mode', 'bed');
    http
      .expectOne('/api/videos')
      .flush({ detail: 'Servidor indisponível' }, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();
    expect(fixture.componentInstance.videos()).toEqual([]);
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain(
      'Servidor indisponível',
    );
  });

  it('does not request precomputed events, frames or audio before playing a bed recording', () => {
    const fixture = setup();
    fixture.componentInstance.selected.set(source);
    fixture.detectChanges();
    fixture.componentInstance.onLoaded();
    http.expectNone('/api/videos/bed/events');
    http.expectNone('/api/videos/bed/frame?timestamp=0');
    http.expectNone('/api/videos/bed/audio');
    http.expectNone('/api/videos/bed/monitor');
    expect(fixture.nativeElement.querySelector('.attendance-alert')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Aguardando reprodução');
  });

  it('only displays attendance for critical detections reached in the current monitoring pass', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    component.monitor.set(live);
    component.events.set([
      { timestamp: 0.1, kind: 'Saída da cerca virtual', severity: 'critical' },
      { timestamp: 0.5, kind: 'Fala: dor no peito', severity: 'critical' },
      { timestamp: 0.7, kind: 'Fala: tontura', severity: 'warning' },
    ]);
    component.currentTime.set(0);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')).toBeNull();
    component.currentTime.set(0.6);
    fixture.detectChanges();
    const alert: HTMLElement = fixture.nativeElement.querySelector('.attendance-alert');
    expect(alert.getAttribute('role')).toBe('alert');
    expect(alert.textContent).toContain('Alerta de atendimento');
    expect(alert.textContent).toContain('SIMULAÇÃO');
    expect(alert.textContent).toContain('2 evento(s)');
    expect(alert.textContent).toContain('Saída da cerca virtual');
    expect(alert.textContent).toContain('Fala: dor no peito');
    expect(alert.textContent).not.toContain('Fala: tontura');
    expect(alert.textContent).toContain('Nenhuma equipe');
    component.currentTime.set(1);
    fixture.detectChanges();
    component.currentTime.set(0);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')).toBeNull();
    component.events.set([]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')).toBeNull();
    component.monitor.set(null);
  });

  it('does not simulate attendance for warnings, physiotherapy or another selected video', () => {
    vi.useFakeTimers();
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    component.monitor.set(live);
    component.events.set([{ timestamp: 0.1, kind: 'Fala: tontura', severity: 'warning' }]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')).toBeNull();
    component.selected.set({ ...source, mode: 'fisio' });
    component.events.set([
      { timestamp: 0.1, kind: 'Saída da cerca virtual', severity: 'critical' },
    ]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')).toBeNull();
    component.select({ ...source, id: 'other' });
    http.expectOne('/api/videos/bed/monitor/session').flush(null);
    expect(component.attendanceAlerts()).toEqual([]);
  });

  it('delivers speech alerts without waiting for YOLO or sentiment, and cancels both pumps on seek', () => {
    vi.useFakeTimers();
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    fixture.detectChanges();
    const player = component.player()!.nativeElement;
    vi.spyOn(player, 'paused', 'get').mockReturnValue(false);
    component.onPlay();
    http.expectOne('/api/videos/bed/monitor').flush(live);
    vi.advanceTimersByTime(0);
    const first = http.expectOne('/api/videos/bed/monitor/session/advance');
    const sound = http.expectOne('/api/videos/bed/monitor/session/audio');
    expect(first.request.body).toEqual({ timestamp: 0 });
    expect(sound.request.body).toEqual({ timestamp: 0, flush_audio: false });
    component.sync(0.4);
    vi.advanceTimersByTime(500);
    http.expectNone('/api/videos/bed/monitor/session/advance');
    http.expectNone('/api/videos/bed/monitor/session/audio');
    sound.flush({
      ...soundState,
      audio_until: 0.4,
      language_pending: true,
      events: [{ timestamp: 0.1, kind: 'Fala: socorro', severity: 'critical', source: 'audio' }],
      transcripts: [
        {
          start: 0.1,
          end: 0.4,
          text: 'Socorro.',
          language: null,
          language_pending: true,
          language_error: null,
        },
      ],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert').textContent).toContain(
      'Fala: socorro',
    );
    expect(component.monitor()?.frame_count).toBe(0);
    expect(fixture.nativeElement.textContent).toContain('sem bloquear alertas');
    vi.advanceTimersByTime(100);
    const pendingAudio = http.expectOne('/api/videos/bed/monitor/session/audio');
    expect(pendingAudio.request.body.timestamp).toBe(0.4);
    first.flush({
      ...live,
      analyzed_until: 0.04,
      frame_count: 1,
      frame: { timestamp: 0, people: [], fence: source.fence, events: [] },
    });
    vi.advanceTimersByTime(100);
    const second = http.expectOne('/api/videos/bed/monitor/session/advance');
    expect(second.request.body.timestamp).toBe(0.4);
    second.flush({
      ...live,
      analyzed_until: 0.44,
      frame_count: 11,
      frame: { timestamp: 0.4, people: [], fence: source.fence, events: [] },
      events: [
        {
          timestamp: 0.35,
          kind: 'Saída da cerca virtual',
          severity: 'critical',
          source: 'image',
        },
      ],
      transcripts: [],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert').textContent).toContain(
      'Fala: socorro',
    );
    expect(component.events()).toHaveLength(2);
    vi.advanceTimersByTime(100);
    const stale = http.expectOne('/api/videos/bed/monitor/session/advance');
    player.currentTime = 0;
    component.onSeeking();
    expect(stale.cancelled).toBe(true);
    expect(pendingAudio.cancelled).toBe(true);
    http.expectOne('/api/videos/bed/monitor/session').flush(null);
    expect(component.monitor()).toBeNull();
    expect(component.events()).toEqual([]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')).toBeNull();
    component.onLoaded();
    const replay = http.expectOne('/api/videos/bed/monitor');
    expect(replay.request.body.timestamp).toBe(0);
    replay.flush({ ...live, id: 'replay' });
    component.onSeeking();
    http.expectOne('/api/videos/bed/monitor/replay').flush(null);
  });

  it('flushes only played audio on pause and keeps visual monitoring available on audio errors', () => {
    vi.useFakeTimers();
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    fixture.detectChanges();
    component.onPlay();
    http.expectOne('/api/videos/bed/monitor').flush(live);
    component.player()!.nativeElement.currentTime = 0.6;
    component.onPause();
    vi.advanceTimersByTime(0);
    const request = http.expectOne('/api/videos/bed/monitor/session/advance');
    const sound = http.expectOne('/api/videos/bed/monitor/session/audio');
    expect(request.request.body).toEqual({ timestamp: 0.6 });
    expect(sound.request.body).toEqual({ timestamp: 0.6, flush_audio: true });
    sound.flush({ ...soundState, audio_until: 0.6, audio_error: 'Speech indisponível.' });
    request.flush({
      ...live,
      analyzed_until: 0.64,
      frame_count: 16,
      frame: { timestamp: 0.6, people: [], fence: source.fence, events: [] },
      events: [{ timestamp: 0.4, kind: 'Saída da cerca virtual', severity: 'critical' }],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Speech indisponível.');
    expect(fixture.nativeElement.querySelector('.attendance-alert')).not.toBeNull();
    vi.advanceTimersByTime(500);
    http.expectNone('/api/videos/bed/monitor/session/advance');
    component.onSeeking();
    http.expectOne('/api/videos/bed/monitor/session').flush(null);
  });

  it('labels provisional attendance and retracts corrected speech without losing visual alerts', () => {
    vi.useFakeTimers();
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    fixture.detectChanges();
    const player = component.player()!.nativeElement;
    vi.spyOn(player, 'paused', 'get').mockReturnValue(false);
    component.onPlay();
    http.expectOne('/api/videos/bed/monitor').flush(live);
    component.sync(0.6);
    vi.advanceTimersByTime(0);
    const image = http.expectOne('/api/videos/bed/monitor/session/advance');
    http.expectOne('/api/videos/bed/monitor/session/audio').flush({
      ...soundState,
      partial_text: 'Preciso de ajuda',
      events: [
        {
          timestamp: 0.1,
          kind: 'Fala: preciso de ajuda',
          severity: 'critical',
          source: 'audio',
          provisional: true,
        },
      ],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert').textContent).toContain(
      'AVISO PROVISÓRIO',
    );
    vi.advanceTimersByTime(100);
    http.expectOne('/api/videos/bed/monitor/session/audio').flush({
      ...soundState,
      partial_text: 'Não preciso de ajuda',
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')).toBeNull();
    image.flush({
      ...live,
      events: [
        {
          timestamp: 0.4,
          kind: 'Saída da cerca virtual',
          severity: 'critical',
          source: 'image',
        },
      ],
    });
    vi.advanceTimersByTime(100);
    const pendingImage = http.expectOne('/api/videos/bed/monitor/session/advance');
    http.expectOne('/api/videos/bed/monitor/session/audio').flush(soundState);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert').textContent).toContain(
      'Saída da cerca virtual',
    );
    expect(fixture.nativeElement.querySelector('.attendance-alert').textContent).not.toContain(
      'PROVISÓRIO',
    );
    component.onSeeking();
    expect(pendingImage.cancelled).toBe(true);
    http.expectOne('/api/videos/bed/monitor/session').flush(null);
  });

  it('shows a real local camera preview only after browser permission is granted', async () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    const track = { stop: vi.fn() };
    const stream = { getTracks: vi.fn(() => [track]) } as unknown as MediaStream;
    const getUserMedia = vi.fn().mockResolvedValue(stream);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();

    await component.startCameraPreview();
    fixture.detectChanges();

    expect(getUserMedia).toHaveBeenCalledWith({ video: true, audio: false });
    expect(component.cameraPreview()).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('PRÉVIA AO VIVO');
    expect(fixture.nativeElement.textContent).toContain('não grava nem processa áudio');

    component.stopCameraPreview();
    expect(component.cameraPreview()).toBe(false);
    expect(track.stop).toHaveBeenCalledOnce();
  });

  it('rejects a video from another module without changing the current selection', () => {
    const component = setup().componentInstance;
    component.selected.set(source);

    component.select({ ...source, mode: 'fisio' });

    expect(component.mode()).toBe('bed');
    expect(component.selected()).toBe(source);
    expect(component.error()).toContain('outro módulo');
  });

  it('keeps the fence inside normalized video bounds', () => {
    const component = setup().componentInstance;
    const input = document.createElement('input');
    input.value = '95';
    input.addEventListener('input', (event) => component.changeFence('x', event));
    input.dispatchEvent(new Event('input'));
    const fence = component.fenceDraft();
    expect(fence.x + fence.width).toBeLessThanOrEqual(1);
    expect(fence.width).toBeGreaterThan(0);
  });

  it('keeps fence position and size adjustable in 0.1% increments', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.selected.set(source);
    component.editingFence.set(true);
    fixture.detectChanges();

    const sliders = fixture.nativeElement.querySelectorAll('fieldset input[type="range"]');
    expect(Number(sliders[0].max)).toBeCloseTo(20, 1);
    expect(Number(sliders[1].max)).toBeCloseTo(10, 1);
    expect(sliders[0].getAttribute('step')).toBe('0.1');
    expect(sliders[2].getAttribute('step')).toBe('0.1');
  });

  it('extends the physiotherapy fence to the bottom for forward movement', () => {
    const component = setup().componentInstance;
    component.fenceDraft.set({ enabled: true, x: 0.2, y: 0.1, width: 0.6, height: 0.8 });
    component.allowForwardMovement();
    expect(component.fenceDraft()).toEqual({
      enabled: true,
      x: 0.2,
      y: 0.15,
      width: 0.6,
      height: 0.85,
    });
  });

  it('expands the fence in steps without crossing video bounds', () => {
    const component = setup().componentInstance;
    component.fenceDraft.set({ enabled: true, x: 0.1, y: 0.1, width: 0.8, height: 0.9 });
    component.expandFence();
    expect(component.fenceDraft()).toEqual({
      enabled: true,
      x: 0.05,
      y: 0.05,
      width: 0.9,
      height: 0.95,
    });
    component.expandFence();
    expect(component.fenceDraft()).toEqual({
      enabled: true,
      x: 0,
      y: 0,
      width: 1,
      height: 1,
    });
    component.expandFence();
    expect(component.fenceDraft()).toEqual({
      enabled: true,
      x: 0,
      y: 0,
      width: 1,
      height: 1,
    });
  });
});
