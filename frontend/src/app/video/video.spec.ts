import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Video } from './video';
import { ClinicalVideo } from './video-api';

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
  fence: { enabled: true, x: 0.1, y: 0.1, width: 0.8, height: 0.9 },
};

describe('Video laboratory', () => {
  let http: HttpTestingController;
  let originalMediaDevices: PropertyDescriptor | undefined;

  beforeEach(() => {
    originalMediaDevices = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');
    TestBed.configureTestingModule({
      imports: [Video],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  });
  afterEach(() => {
    http.verify({ ignoreCancelled: true });
    if (originalMediaDevices)
      Object.defineProperty(navigator, 'mediaDevices', originalMediaDevices);
    else Reflect.deleteProperty(navigator, 'mediaDevices');
    vi.restoreAllMocks();
  });

  function setup() {
    const fixture = TestBed.createComponent(Video);
    http.expectOne('/api/videos').flush([source]);
    fixture.detectChanges();
    return fixture;
  }

  it('renders translated monitoring choices and native scrubbing controls', () => {
    const fixture = setup();
    fixture.componentInstance.selected.set(source);
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector<HTMLVideoElement>('video[controls]')?.controls).toBe(true);
    expect(element.textContent).toContain('Monitoramento de leitos');
    expect(element.textContent).toContain('Análise de fisioterapia');
    expect(element.textContent).toContain('Ajustar cerca virtual');
  });

  it('clarifies that an empty event log means no alert was detected', () => {
    const fixture = setup();
    fixture.componentInstance.selected.set(source);
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
    component.selected.set(source);
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
    const fixture = TestBed.createComponent(Video);
    http
      .expectOne('/api/videos')
      .flush({ detail: 'Servidor indisponível' }, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();
    expect(fixture.componentInstance.videos()).toEqual([]);
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain(
      'Servidor indisponível',
    );
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

  it('clears an incompatible video when the monitoring mode changes', () => {
    const component = setup().componentInstance;
    component.selected.set(source);

    component.changeMode('fisio');

    expect(component.mode()).toBe('fisio');
    expect(component.selected()).toBeNull();
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
