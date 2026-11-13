import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { CameraMonitor, cameraWav } from './camera-monitor';
import { CameraMonitorState, Fence, MonitorAlert } from './video-api';

const fence: Fence = { enabled: true, x: .4, y: .2, width: .5, height: .6 };
const state: CameraMonitorState = {
  id: 'camera-session', closed: false, frame: null, alerts: [], events: [],
  frame_count: 0, elapsed: 0, recording_id: null, audio_error: null,
  partial_text: '', transcripts: [],
};
const alert: MonitorAlert = {
  id: 'camera-alert', session_id: state.id, video_id: 'camera-leito-1',
  timestamp: 1, kind: 'Saída da cerca virtual', source: 'image',
  status: 'confirmed', created_at: '2026-11-13T02:00:00Z',
  updated_at: '2026-11-13T02:00:00Z', acknowledged_at: null, version: 1,
};

describe('Camera monitoring', () => {
  let http: HttpTestingController;
  let mediaDevices: PropertyDescriptor | undefined;
  beforeEach(() => {
    mediaDevices = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');
    TestBed.configureTestingModule({
      imports: [CameraMonitor], providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  });
  afterEach(() => {
    TestBed.resetTestingModule();
    http.verify({ ignoreCancelled: true });
    if (mediaDevices) Object.defineProperty(navigator, 'mediaDevices', mediaDevices);
    else Reflect.deleteProperty(navigator, 'mediaDevices');
    vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
  });
  async function setup(saved: Fence | null = null) {
    const fixture = TestBed.createComponent(CameraMonitor);
    http.expectOne('/api/camera/fence').flush({ fence: saved });
    await Promise.resolve();
    fixture.detectChanges();
    return fixture;
  }

  it('requires a saved manual fence and persists the confirmed coordinates', async () => {
    const fixture = await setup();
    const component = fixture.componentInstance;
    component.preview.set(true);
    component.editFence();
    fixture.detectChanges();
    expect(component.canStart()).toBe(false);
    await component.startMonitoring();
    http.expectNone('/api/camera/monitor');
    expect(component.error()).toContain('salve a cerca');
    component.fence.set(fence);
    const saving = component.saveFence();
    expect(component.canStart()).toBe(false);
    const request = http.expectOne('/api/camera/fence');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual(fence);
    request.flush({ fence });
    await saving; fixture.detectChanges();
    expect(component.savedFence()).toEqual(fence);
    expect(component.canStart()).toBe(true);
    expect(component.notice()).toContain('salvas no servidor');
  });

  it('keeps monitoring blocked and shows the server failure when saving fails', async () => {
    const fixture = await setup();
    const component = fixture.componentInstance;
    component.preview.set(true); component.editFence(); component.fence.set(fence);
    const saving = component.saveFence();
    http.expectOne('/api/camera/fence').flush({ detail: 'Falha ao salvar' },
      { status: 500, statusText: 'Error' });
    await saving;
    expect(component.savedFence()).toBeNull();
    expect(component.canStart()).toBe(false);
    expect(component.error()).toBe('Falha ao salvar');
  });

  it('draws the manual camera fence in image coordinates with letterboxing', async () => {
    const fixture = await setup();
    const component = fixture.componentInstance;
    component.preview.set(true); component.editFence();
    component.dimensions.set({ width: 200, height: 100 }); fixture.detectChanges();
    const svg: SVGSVGElement = fixture.nativeElement.querySelector('.fence-overlay');
    vi.spyOn(svg, 'getBoundingClientRect').mockReturnValue(new DOMRect(100, 200, 400, 400));
    Object.defineProperties(svg, {
      setPointerCapture: { value: vi.fn() }, hasPointerCapture: { value: () => false },
    });
    const pointer = (type: string, x: number, y: number) => {
      const event = new Event(type, { bubbles: true });
      Object.defineProperties(event, {
        clientX: { value: x }, clientY: { value: y }, pointerId: { value: 1 }, button: { value: 0 },
      });
      svg.dispatchEvent(event);
    };
    pointer('pointerdown', 180, 340); pointer('pointerup', 420, 460);
    expect(component.fence().x).toBeCloseTo(.2);
    expect(component.fence().y).toBeCloseTo(.2);
    expect(component.fence().width).toBeCloseTo(.6);
    expect(component.fence().height).toBeCloseTo(.6);
    expect(component.savedFence()).toBeNull();
  });

  it('records camera attendance, updates history, hides green after five seconds and restores new alerts', async () => {
    vi.useFakeTimers();
    const fixture = await setup(fence);
    const component = fixture.componentInstance;
    component.state.set({ ...state, alerts: [alert] }); component.alerts.set([alert]);
    fixture.detectChanges();
    const acknowledgment = component.acknowledge();
    const request = http.expectOne(`/api/camera/monitor/${state.id}/acknowledge`);
    expect(request.request.body).toEqual({ alert_ids: [alert.id] });
    const acknowledged = { ...alert, acknowledged_at: '2026-11-13T02:01:00Z', version: 2 };
    request.flush([acknowledged]);
    await Promise.resolve(); await Promise.resolve();
    http.expectOne('/api/camera/alert-log').flush([{
      id: 1, action: 'immediate_care_requested', created_at: acknowledged.acknowledged_at,
      payload: acknowledged,
    }]);
    await acknowledgment; fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.registered')).not.toBeNull();
    expect(component.history()).toHaveLength(1);
    vi.advanceTimersByTime(3000);
    component.alerts.set([acknowledged]); fixture.detectChanges();
    vi.advanceTimersByTime(2000); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')).toBeNull();
    component.alerts.update(a => [...a, { ...alert, id: 'new-alert', timestamp: 3 }]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.attendance-alert')?.getAttribute('role')).toBe('alert');
    component.state.set({ ...state, closed: true }); component.alerts.set([]);
    fixture.detectChanges();
  });

  it('requests only camera permission for preview and releases its tracks on disconnect', async () => {
    const stop = vi.fn(), getUserMedia = vi.fn();
    const stream = { getTracks: () => [{ stop }], getAudioTracks: () => [], getVideoTracks: () => [] };
    getUserMedia.mockResolvedValue(stream);
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } });
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
    const fixture = await setup();
    const component = fixture.componentInstance;
    await component.connect();
    expect(getUserMedia).toHaveBeenCalledWith({ video: true, audio: false });
    expect(component.preview()).toBe(true);
    expect(component.editing()).toBe(true);
    expect(component.canStart()).toBe(false);
    await component.disconnect();
    expect(stop).toHaveBeenCalledOnce();
    expect(component.preview()).toBe(false);
  });

  it('releases a camera permission response that arrives after disconnection', async () => {
    const stop = vi.fn();
    let resolvePermission: ((stream: { getTracks: () => { stop: typeof stop }[] }) => void) | undefined;
    const permission = new Promise<{ getTracks: () => { stop: typeof stop }[] }>(resolve => {
      resolvePermission = resolve;
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true, value: { getUserMedia: vi.fn(() => permission) },
    });
    const fixture = await setup();
    const component = fixture.componentInstance;
    const connecting = component.connect();
    await component.disconnect();
    resolvePermission?.({ getTracks: () => [{ stop }] });
    await connecting;
    expect(stop).toHaveBeenCalledOnce();
    expect(component.preview()).toBe(false);
    expect(component.starting()).toBe(false);
  });

  it('encodes mono16k PCM WAV from actual samples without clipping overflow', async () => {
    const blob = cameraWav(new Float32Array([2, -2, .5, -.5]), 16000);
    const view = new DataView(await blob.arrayBuffer());
    expect(blob.type).toBe('audio/wav');
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(40, true)).toBe(8);
    expect(view.getInt16(44, true)).toBe(32767);
    expect(view.getInt16(46, true)).toBe(-32768);
  });

  it('streams real frame and PCM payloads only after saved fence and drains them before closing', async () => {
    vi.useFakeTimers();
    const track = { stop: vi.fn(), addEventListener: vi.fn() };
    const microphone = { getTracks: () => [track], getAudioTracks: () => [track] };
    const stream = {
      getTracks: () => [track], getAudioTracks: () => [track],
      getVideoTracks: () => [track],
      addTrack: vi.fn(), removeTrack: vi.fn(),
    };
    const getUserMedia = vi.fn().mockResolvedValueOnce(stream).mockResolvedValueOnce(microphone);
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } });
    class Context {
      state = 'running';
      sampleRate = 16000;
      destination = {};
      audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };
      resume = vi.fn().mockResolvedValue(undefined);
      close = vi.fn().mockResolvedValue(undefined);
      createMediaStreamSource = vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() }));
    }
    const received: { handler: ((event: { data: unknown }) => void) | null } = { handler: null };
    class Node {
      port = {
        get onmessage() { return received.handler; },
        set onmessage(handler: ((event: { data: unknown }) => void) | null) { received.handler = handler; },
        postMessage: vi.fn(() => received.handler?.({ data: { flushed: true } })),
      };
      connect = vi.fn();
      disconnect = vi.fn();
    }
    vi.stubGlobal('AudioContext', Context);
    vi.stubGlobal('AudioWorkletNode', Node);
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
    const drawingContext: Partial<CanvasRenderingContext2D> = {
      drawImage: () => {},
    };
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(drawingContext as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(callback =>
      callback(new Blob(['jpeg'], { type: 'image/jpeg' })));
    const fixture = await setup(fence);
    const component = fixture.componentInstance;
    const player = component.player()!.nativeElement;
    Object.defineProperties(player, {
      videoWidth: { value: 1280, configurable: true }, videoHeight: { value: 720, configurable: true },
    });
    await component.connect();
    component.record.set(true);
    const started = component.startMonitoring();
    for (let i = 0; i < 10; i++) await Promise.resolve();
    const create = http.expectOne('/api/camera/monitor');
    expect(create.request.body).toEqual({ fence, record: true });
    create.flush(state);
    await started;
    for (let i = 0; i < 5; i++) await Promise.resolve();
    const frame = http.expectOne(`/api/camera/monitor/${state.id}/frame`);
    expect(frame.request.body.get('file').type).toBe('image/jpeg');
    received.handler?.({ data: { samples: new Float32Array(48000) } });
    for (let i = 0; i < 5; i++) await Promise.resolve();
    const audio = http.expectOne(`/api/camera/monitor/${state.id}/audio`);
    expect(audio.request.body.get('file').type).toBe('audio/wav');
    expect(audio.request.body.get('timestamp')).toBe('0');
    const stopped = component.stopMonitoring();
    http.expectNone(`/api/camera/monitor/${state.id}`);
    frame.flush({ ...state, frame_count: 1 });
    audio.flush({ ...state, transcripts: [{
      start: 0, end: 3, text: 'Estou bem', language: null,
      language_pending: false, language_error: null,
    }] });
    for (let i = 0; i < 15; i++) await Promise.resolve();
    const close = http.expectOne(`/api/camera/monitor/${state.id}`);
    expect(close.request.method).toBe('DELETE');
    close.flush({ ...state, closed: true, recording_id: 'recorded-camera' });
    for (let i = 0; i < 5; i++) await Promise.resolve();
    http.expectOne('/api/camera/alert-log').flush([]);
    await stopped;
    expect(component.active()).toBe(false);
    expect(component.notice()).toContain('Gravação salva');
    expect(getUserMedia).toHaveBeenLastCalledWith({ video: false, audio: true });
    await component.disconnect();
  });
});
