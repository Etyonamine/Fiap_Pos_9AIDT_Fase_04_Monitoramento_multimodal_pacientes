import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { By, Title } from '@angular/platform-browser';
import { provideRouter, Router } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from '../app.routes';
import { Telemetry } from '../telemetry/telemetry';
import { AnalysisMode, ClinicalVideo } from './video-api';
import { Video } from './video';
import { VideoWorkspace } from './video-workspace';
import { CameraMonitor } from './camera-monitor';

function recording(mode: AnalysisMode): ClinicalVideo {
  return {
    id: mode,
    name: `${mode}.mp4`,
    mode,
    created_at: '2026-11-10T09:00:00Z',
    status: 'ready',
    progress: 1,
    duration: 1,
    fps: 25,
    width: 100,
    height: 100,
    error: null,
    is_sample: 0,
    url: `/api/videos/${mode}/media`,
    audio: null,
    thresholds: { trunk_angle: 35, knee_angle: 60 },
    posture_config: null,
    fence: { enabled: true, x: 0.1, y: 0.1, width: 0.8, height: 0.9 },
  };
}

describe('Video and telemetry navigation', () => {
  let http: HttpTestingController;
  let harness: RouterTestingHarness;
  let originalMediaDevices: PropertyDescriptor | undefined;

  beforeEach(async () => {
    originalMediaDevices = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');
    TestBed.configureTestingModule({
      providers: [provideRouter(routes), provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    harness = await RouterTestingHarness.create();
  });

  afterEach(() => {
    TestBed.resetTestingModule();
    http.verify({ ignoreCancelled: true });
    if (originalMediaDevices)
      Object.defineProperty(navigator, 'mediaDevices', originalMediaDevices);
    else Reflect.deleteProperty(navigator, 'mediaDevices');
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function flushLibrary() {
    http.expectOne('/api/videos').flush([recording('bed'), recording('fisio')]);
    harness.detectChanges();
  }

  function workspace() {
    return harness.routeDebugElement!.query(By.directive(VideoWorkspace))
      .componentInstance as VideoWorkspace;
  }

  it('opens physiotherapy directly, filters bed recordings and offers no camera or mode switch', async () => {
    await harness.navigateByUrl('/video', Video);
    flushLibrary();
    const element = harness.routeNativeElement!;
    expect(element.querySelector('h1')?.textContent).toBe('Análise de vídeos de fisioterapia');
    expect(TestBed.inject(Title).getTitle()).toBe(
      'YtosMedialAI · Análise de vídeos de fisioterapia',
    );
    expect(workspace().mode()).toBe('fisio');
    expect(element.querySelectorAll('.file')).toHaveLength(1);
    expect(element.querySelector('.file')?.textContent).toContain('fisio.mp4');
    expect(element.querySelector('.bed-card')).toBeNull();
    expect(element.querySelector('.mode-navigation')).toBeNull();
    expect(element.textContent).toContain('Métricas do exercício');
    expect(element.textContent).toContain('Registro de eventos');
    expect(element.querySelector('.event-log')).not.toBeNull();
    expect(element.textContent).not.toContain('Vídeo analisado; nenhum evento');
    expect(element.querySelector<HTMLAnchorElement>('a[href="/telemetry"]')).not.toBeNull();
  });

  it('places bed controls and explicitly simulated clinical data in telemetry', async () => {
    await harness.navigateByUrl('/telemetry', Telemetry);
    flushLibrary();
    const element = harness.routeNativeElement!;
    expect(TestBed.inject(Title).getTitle()).toBe('YtosMedialAI · Telemetria e anomalias');
    expect(workspace().mode()).toBe('bed');
    expect(element.querySelectorAll('.file')).toHaveLength(1);
    expect(element.querySelector('.file')?.textContent).toContain('bed.mp4');
    expect(element.querySelector('.bed-card')).toBeNull();
    expect(element.querySelector('.mode-navigation')).toBeNull();
    expect(element.querySelector('#vital-signs')?.textContent).toContain('SIMULADO');
    expect(element.querySelector('#prescriptions')?.textContent).toContain('SIMULADO');
    expect(element.textContent).not.toContain('3 sinais conectados');
    expect(element.textContent).not.toContain('Pico crítico detectado');
    expect(element.textContent).toContain('nenhuma equipe médica ou emergência é notificada');
    expect(element.textContent).toContain('não são extraídos do vídeo nem de um banco');
    expect(element.textContent).not.toContain('Telemetria de movimento');
    expect(element.textContent).not.toContain('Ângulo interno do joelho');
    expect(element.textContent).not.toContain('Registro de eventos');
    expect(element.querySelector('.event-log')).toBeNull();
    workspace().selected.set(recording('bed'));
    harness.detectChanges();
    expect(element.textContent).toContain('Histórico de alertas e atendimento');
    expect(element.textContent).toContain('Áudio da gravação de leito');
    expect(element.querySelector('.event-log')).toBeNull();
    element.querySelectorAll<HTMLButtonElement>('.view-options button')[0].click();
    harness.detectChanges();
    expect(element.textContent).not.toContain('Ângulo interno do joelho');
    expect(element.textContent).not.toContain('Registro de eventos');
    expect(element.textContent).toContain('Controles');
  });

  it('switches source tabs and recreates the workspace while preserving clinical data', async () => {
    await harness.navigateByUrl('/telemetry', Telemetry);
    flushLibrary();
    const bed = workspace();
    bed.selected.set(recording('bed'));
    const buttons = harness.routeNativeElement!.querySelectorAll<HTMLButtonElement>('.view-options button');
    buttons[1].click();
    harness.detectChanges();
    http.expectOne('/api/camera/fence').flush({ fence: null });
    harness.detectChanges();
    expect(harness.routeDebugElement!.query(By.directive(VideoWorkspace))).toBeNull();
    expect(harness.routeDebugElement!.query(By.directive(CameraMonitor))).not.toBeNull();
    expect(harness.routeNativeElement!.querySelector('.bed-card')).not.toBeNull();
    expect(harness.routeNativeElement!.querySelector('.source-library')).toBeNull();
    expect(harness.routeNativeElement!.querySelector('#vital-signs')).not.toBeNull();
    expect(harness.routeNativeElement!.querySelectorAll('.simulation-alerts')).toHaveLength(1);
    expect(harness.routeNativeElement!.querySelector('.stage .simulation-alerts')).not.toBeNull();
    buttons[0].click();
    harness.detectChanges();
    http.expectOne('/api/videos').flush([recording('bed')]);
    harness.detectChanges();
    expect(workspace()).not.toBe(bed);
    expect(workspace().sourceView()).toBe('recordings');
    expect(harness.routeNativeElement!.querySelector('#vital-signs')).not.toBeNull();
    expect(TestBed.inject(Router).url).toBe('/telemetry');
  });

  it('supports keyboard source switching and releases the camera when returning to recordings', async () => {
    const stop = vi.fn();
    const stream = { getTracks: () => [{ stop }], getAudioTracks: () => [], getVideoTracks: () => [] };
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
    await harness.navigateByUrl('/telemetry', Telemetry);
    flushLibrary();
    const element = harness.routeNativeElement!;
    element.querySelector('#recordings-tab')!.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'ArrowRight', bubbles: true,
    }));
    harness.detectChanges();
    http.expectOne('/api/camera/fence').flush({ fence: null });
    harness.detectChanges();
    expect(element.querySelector('#camera-tab')?.getAttribute('aria-selected')).toBe('true');
    expect(element.querySelector('.source-library')).toBeNull();
    const camera = harness.routeDebugElement!.query(By.directive(CameraMonitor)).componentInstance as CameraMonitor;
    await camera.connect();
    harness.detectChanges();
    expect(camera.preview()).toBe(true);
    element.querySelector<HTMLButtonElement>('#recordings-tab')!.click();
    harness.detectChanges();
    flushLibrary();
    expect(stop).toHaveBeenCalledTimes(1);
    expect(element.querySelector('.source-library')).not.toBeNull();
    expect(element.querySelector('.bed-card')).toBeNull();
    expect(element.querySelectorAll('.simulation-alerts')).toHaveLength(1);
  });

  it('always combines clinical data with the selected video source and preserves clinical alerts', async () => {
    await harness.navigateByUrl('/telemetry', Telemetry);
    flushLibrary();
    const bed = workspace();
    bed.selected.set(recording('bed'));
    const element = harness.routeNativeElement!;
    const buttons = element.querySelectorAll<HTMLButtonElement>('.view-options button');
    expect(element.querySelector('.monitoring-layout.combined #movement')).not.toBeNull();
    expect(element.querySelector('.monitoring-layout.combined #vital-signs')).not.toBeNull();
    const library = element.querySelector('.source-library');
    expect(element.querySelector('.source-main .bed-card')).toBeNull();
    expect(library?.querySelector('.recording-list .file')).not.toBeNull();
    expect(library?.querySelector('.recording-upload button')).not.toBeNull();
    const layout = element.querySelector('.monitoring-layout')!;
    const children = [...layout.children];
    expect(children.indexOf(element.querySelector('.movement-heading')!)).toBeLessThan(
      children.indexOf(element.querySelector('.simulation-controls')!),
    );
    expect(children.indexOf(element.querySelector('.movement-heading')!)).toBeLessThan(
      children.indexOf(element.querySelector('#movement')!),
    );
    expect(element.querySelectorAll('.simulation-alerts')).toHaveLength(1);
    expect(element.querySelector('.stage .simulation-alerts')).not.toBeNull();
    const telemetry = harness.routeDebugElement!.componentInstance as Telemetry;
    telemetry.alerts.set(Array.from({ length: 20 }, (_, i) => ({
      step: i,
      message: `Evento simulado ${i}`,
    })));
    harness.detectChanges();
    const alertList = element.querySelector<HTMLElement>('.stage .alerts-list')!;
    expect(alertList.querySelectorAll('li')).toHaveLength(20);
    expect(alertList.getAttribute('tabindex')).toBe('0');
    expect(alertList.getAttribute('aria-label')).toBe('Lista de alertas da simulação clínica');
    buttons[1].click();
    harness.detectChanges();
    http.expectOne('/api/camera/fence').flush({ fence: null });
    harness.detectChanges();
    expect(harness.routeDebugElement!.query(By.directive(VideoWorkspace))).toBeNull();
    expect(element.querySelector('.source-library')).toBeNull();
    expect(element.querySelector('#vital-signs')).not.toBeNull();
    expect(element.querySelector('.simulation-alerts')).not.toBeNull();
    buttons[0].click();
    harness.detectChanges();
    http.expectOne('/api/videos').flush([recording('bed')]);
    harness.detectChanges();
    expect(workspace().selected()).toBeNull();
    expect(element.querySelector('.monitoring-layout.combined #vital-signs')).not.toBeNull();
    expect(element.querySelector('.stage .simulation-alerts')).not.toBeNull();
    expect(element.querySelectorAll('.stage .alerts-list li')).toHaveLength(20);
  });

  it('uploads with the mode belonging to each route and does not expose the other library', async () => {
    vi.stubGlobal('URL', Object.assign(class extends URL {}, {
      createObjectURL: vi.fn(() => 'blob:video'),
      revokeObjectURL: vi.fn(),
    }));
    for (const mode of ['fisio', 'bed'] as const) {
      await harness.navigateByUrl(mode === 'fisio' ? '/video' : '/telemetry');
      flushLibrary();
      if (mode === 'fisio') {
        const select = harness.routeNativeElement!.querySelector<HTMLSelectElement>('#posture-choice')!;
        select.value = 'lying';
        select.dispatchEvent(new Event('change'));
        harness.detectChanges();
      }
      const input =
        harness.routeNativeElement!.querySelector<HTMLInputElement>('input[type="file"]')!;
      Object.defineProperty(input, 'files', {
        configurable: true,
        value: [new File(['video'], 'exemplo.mp4', { type: 'video/mp4' })],
      });
      input.dispatchEvent(new Event('change'));
      if (mode === 'fisio') {
        http.expectNone('/api/videos');
        harness.detectChanges();
        workspace().submitPostureVideo();
      }
      const request = http.expectOne('/api/videos');
      expect(request.request.method).toBe('POST');
      expect(request.request.body.get('mode')).toBe(mode);
      expect(request.request.body.get('file').name).toBe('exemplo.mp4');
      if (mode === 'fisio') {
        expect(JSON.parse(request.request.body.get('posture'))).toEqual({ type: 'lying', intervals: [] });
      } else {
        expect(request.request.body.get('posture')).toBeNull();
      }
      request.flush(recording(mode));
      harness.detectChanges();
      expect(workspace().selected()?.mode).toBe(mode);
      expect(
        workspace()
          .sources()
          .every((video) => video.mode === mode),
      ).toBe(true);
    }
  });

  it('requires ordered hybrid intervals and submits the manually marked timeline', async () => {
    vi.stubGlobal('URL', Object.assign(class extends URL {}, {
      createObjectURL: vi.fn(() => 'blob:video'),
      revokeObjectURL: vi.fn(),
    }));
    await harness.navigateByUrl('/video');
    flushLibrary();
    const root = harness.routeNativeElement!;
    const choice = root.querySelector<HTMLSelectElement>('#posture-choice')!;
    expect(root.querySelector<HTMLButtonElement>('.upload')!.disabled).toBe(true);
    choice.value = 'hybrid';
    choice.dispatchEvent(new Event('change'));
    const input = root.querySelector<HTMLInputElement>('input[type="file"]')!;
    Object.defineProperty(input, 'files', {
      configurable: true, value: [new File(['video'], 'hybrid.mp4', { type: 'video/mp4' })],
    });
    input.dispatchEvent(new Event('change'));
    harness.detectChanges();
    expect(root.textContent).toContain('Informe início e fim válidos');
    workspace().submitPostureVideo();
    http.expectNone('/api/videos');

    const preview = root.querySelector<HTMLVideoElement>('.posture-editor video')!;
    vi.spyOn(preview, 'currentTime', 'get').mockReturnValue(2);
    workspace().markIntervalTime(0, 'end');
    expect(workspace().intervals()[0].end).toBe(2);
    workspace().addInterval();
    harness.detectChanges();
    const times = root.querySelectorAll<HTMLInputElement>('.posture-editor input[type="number"]');
    times[2].value = '1';
    times[2].dispatchEvent(new Event('input'));
    times[3].value = '4';
    times[3].dispatchEvent(new Event('input'));
    harness.detectChanges();
    expect(root.textContent).toContain('Ordene os intervalos sem sobreposição');
    times[2].value = '3';
    times[2].dispatchEvent(new Event('input'));
    const selects = root.querySelectorAll<HTMLSelectElement>('.posture-editor fieldset select');
    selects[1].value = 'lying';
    selects[1].dispatchEvent(new Event('change'));
    workspace().previewDuration.set(3.5);
    harness.detectChanges();
    expect(root.textContent).toContain('Os intervalos devem estar dentro da duração');
    workspace().previewDuration.set(4);
    harness.detectChanges();
    expect(workspace().intervalError()).toBe('');
    workspace().submitPostureVideo();
    const request = http.expectOne('/api/videos');
    expect(JSON.parse(request.request.body.get('posture'))).toEqual({
      type: 'hybrid',
      intervals: [
        { start: 0, end: 2, posture: 'standing' },
        { start: 3, end: 4, posture: 'lying' },
      ],
    });
    request.flush(recording('fisio'));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:video');
  });

  it('destroys bed monitoring when navigating to physiotherapy and returns with a clean workspace', async () => {
    await harness.navigateByUrl('/telemetry', Telemetry);
    flushLibrary();
    const bed = workspace();
    bed.selected.set(recording('bed'));
    bed.monitor.set({
      id: 'session',
      video_id: 'bed',
      start: 0,
      closed: false,
      target: 0,
      analyzed_until: 0,
      frame_count: 0,
      frame: null,
      alerts: [],
      events: [],
      audio_until: 0,
      audio_pending: false,
      audio_error: null,
      partial_text: '',
      language_pending: false,
      transcripts: [],
    });
    await harness.navigateByUrl('/video', Video);
    http.expectOne('/api/videos/bed/monitor/session').flush(null);
    flushLibrary();
    expect(workspace().monitor()).toBeNull();
    expect(workspace().selected()).toBeNull();
    expect(workspace().mode()).toBe('fisio');
    await harness.navigateByUrl('/telemetry', Telemetry);
    flushLibrary();
    expect(workspace()).not.toBe(bed);
    expect(workspace().events()).toEqual([]);
    expect(workspace().selected()).toBeNull();
  });

  it('releases the local camera on navigation and never requests it from physiotherapy', async () => {
    const stop = vi.fn();
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
    await harness.navigateByUrl('/telemetry', Telemetry);
    flushLibrary();
    await workspace().startCameraPreview();
    expect(workspace().cameraPreview()).toBe(true);
    await harness.navigateByUrl('/video', Video);
    flushLibrary();
    expect(stop).toHaveBeenCalledOnce();
    await workspace().startCameraPreview();
    expect(getUserMedia).toHaveBeenCalledOnce();
    expect(workspace().cameraPreview()).toBe(false);
  });
});
