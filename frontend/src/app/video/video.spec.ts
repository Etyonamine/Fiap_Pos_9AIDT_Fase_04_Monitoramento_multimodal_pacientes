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
    expect(element.textContent).not.toContain('Vídeo analisado; nenhum evento');
    expect(element.querySelector<HTMLAnchorElement>('a[href="/telemetry"]')).not.toBeNull();
  });

  it('places bed controls in telemetry and never claims sensors, prescriptions or alerts are connected', async () => {
    await harness.navigateByUrl('/telemetry', Telemetry);
    flushLibrary();
    const element = harness.routeNativeElement!;
    expect(TestBed.inject(Title).getTitle()).toBe('YtosMedialAI · Telemetria e anomalias');
    expect(workspace().mode()).toBe('bed');
    expect(element.querySelectorAll('.file')).toHaveLength(1);
    expect(element.querySelector('.file')?.textContent).toContain('bed.mp4');
    expect(element.querySelector('.bed-card')).not.toBeNull();
    expect(element.querySelector('.mode-navigation')).toBeNull();
    expect(element.querySelector('#vital-signs')?.textContent).toContain('NÃO INTEGRADO');
    expect(element.querySelector('#prescriptions')?.textContent).toContain('NÃO INTEGRADO');
    expect(element.textContent).not.toContain('3 sinais conectados');
    expect(element.textContent).not.toContain('Pico crítico detectado');
    expect(element.textContent).toContain('nenhuma equipe médica ou emergência é notificada');
    for (const link of element.querySelectorAll<HTMLAnchorElement>('.domain-navigation a')) {
      expect(link.pathname).toBe('/telemetry');
      expect(element.querySelector(link.hash)).not.toBeNull();
      expect(element.querySelector(link.hash)?.getAttribute('tabindex')).toBe('-1');
    }
  });

  it('navigates to each telemetry section without leaving the route or resetting the workspace', async () => {
    await harness.navigateByUrl('/telemetry', Telemetry);
    flushLibrary();
    const bed = workspace();
    bed.selected.set(recording('bed'));
    for (const fragment of ['vital-signs', 'prescriptions', 'movement']) {
      harness
        .routeNativeElement!.querySelector<HTMLAnchorElement>(
          `.domain-navigation a[href="/telemetry#${fragment}"]`,
        )!
        .click();
      await harness.fixture.whenStable();
      harness.detectChanges();
      expect(TestBed.inject(Router).url).toBe(`/telemetry#${fragment}`);
      expect(document.activeElement?.id).toBe(fragment);
      expect(workspace()).toBe(bed);
      expect(workspace().selected()?.id).toBe('bed');
    }
    http.expectNone('/api/videos');
  });

  it('uploads with the mode belonging to each route and does not expose the other library', async () => {
    for (const mode of ['fisio', 'bed'] as const) {
      await harness.navigateByUrl(mode === 'fisio' ? '/video' : '/telemetry');
      flushLibrary();
      const input =
        harness.routeNativeElement!.querySelector<HTMLInputElement>('input[type="file"]')!;
      Object.defineProperty(input, 'files', {
        configurable: true,
        value: [new File(['video'], 'exemplo.mp4', { type: 'video/mp4' })],
      });
      input.dispatchEvent(new Event('change'));
      const request = http.expectOne('/api/videos');
      expect(request.request.method).toBe('POST');
      expect(request.request.body.get('mode')).toBe(mode);
      expect(request.request.body.get('file').name).toBe('exemplo.mp4');
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
