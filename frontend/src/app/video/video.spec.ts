import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Video } from './video';
import { ClinicalVideo } from './video-api';

const source: ClinicalVideo = {
  id: 'bed',
  name: 'bed.mp4',
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
  fence: { enabled: true, x: 0.1, y: 0.1, width: 0.8, height: 0.8 },
};

describe('Video laboratory', () => {
  let http: HttpTestingController;

  beforeEach(() => {
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
    vi.restoreAllMocks();
  });

  function setup() {
    const fixture = TestBed.createComponent(Video);
    http.expectOne('/api/videos').flush([source]);
    fixture.detectChanges();
    return fixture;
  }

  it('renders source selectors and native scrubbing controls', () => {
    const fixture = setup();
    fixture.componentInstance.selected.set(source);
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('video')?.controls).toBe(true);
    expect(element.textContent).toContain('Upload Clinical Video');
    expect(element.textContent).toContain('Fisio Analysis Mode');
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
});
