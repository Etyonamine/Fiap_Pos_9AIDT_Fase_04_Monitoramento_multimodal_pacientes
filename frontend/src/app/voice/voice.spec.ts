import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ClinicalAudio } from './audio-api';
import { Voice } from './voice';

const source: ClinicalAudio = {
  id: 'consulta',
  name: 'consulta.wav',
  status: 'uploaded',
  created_at: '2026-11-08T19:00:00Z',
  duration: 70,
  error: null,
  url: '/api/audios/consulta/media',
  acoustic: {
    duration: 70,
    rms_energy: 0.1,
    low_energy_ratio: 0.4,
    longest_low_energy_seconds: 2.1,
    clipping_ratio: 0,
    energy_change_db: null,
    waveform: [0.1, 0.2, 0.15],
    indicators: ['Revisar pausas.'],
    limitation: 'Heurísticas não validadas clinicamente.',
  },
  result: null,
};
const ready: ClinicalAudio = {
  ...source,
  status: 'ready',
  result: {
    transcription: {
      provider: 'Azure Speech to Text',
      language: 'pt-BR',
      text: 'Tenho falta de ar.',
      segments: [{ text: 'Tenho falta de ar.', offset: 61, duration: 2, confidence: 0.92 }],
    },
    critical_terms: [
      {
        term: 'falta de ar',
        severity: 'critical',
        negated: false,
        offset: 6,
        context: 'Tenho falta de ar.',
      },
    ],
    rules_version: 1,
    language: {
      provider: 'Azure Text Analytics',
      key_phrases: ['falta de ar'],
      sentiment: {
        label: 'negative',
        scores: { positive: 0.01, neutral: 0.09, negative: 0.9 },
        chunks: [],
        aggregation: 'Média ponderada dos trechos.',
      },
    },
  },
};

describe('Audio consultations', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [Voice],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  });
  afterEach(() => {
    http.verify({ ignoreCancelled: true });
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  function setup(audios: ClinicalAudio[] = [source]) {
    const fixture = TestBed.createComponent(Voice);
    http.expectOne('/api/audios').flush(audios);
    http.expectOne('/api/audios/configuration').flush({
      configured: true,
      message: 'Conexão validada apenas na análise.',
    });
    fixture.detectChanges();
    return fixture;
  }

  it('shows imported audio with native playback and no fabricated confidence or transcription', () => {
    const fixture = setup();
    const element: HTMLElement = fixture.nativeElement;
    const player = element.querySelector<HTMLAudioElement>('audio')!;
    expect(player.controls).toBe(true);
    expect(player.getAttribute('src')).toBe(source.url);
    expect(element.textContent).toContain('Nenhuma transcrição disponível');
    expect(element.textContent).not.toContain('98%');
    expect(element.textContent).not.toContain('PT-8842');
    expect(element.querySelector('.primary')?.hasAttribute('disabled')).toBe(true);
  });

  it('keeps the clinical panel in the workspace and supplementary details collapsed', () => {
    const fixture = setup([ready]);
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('.dashboard .clinical')).not.toBeNull();
    expect(element.querySelector('.dashboard .transcript')).not.toBeNull();
    expect(element.querySelector<HTMLDetailsElement>('.library')?.open).toBe(false);
    const details = element.querySelectorAll<HTMLDetailsElement>('.supplementary details');
    expect(details.length).toBe(2);
    details.forEach((detail) => expect(detail.open).toBe(false));
    expect(element.querySelector('.clinical [role=alert]')?.textContent).toContain(
      'Prioridade de revisão: alta',
    );
    expect(element.querySelector('.file .priority-label')).not.toBeNull();
    expect(element.querySelector('.file')?.getAttribute('aria-pressed')).toBe('true');
    details[0].open = true;
    expect(details[0].textContent).toContain('Negativo');
  });

  it('does not raise a high priority alert for negated terms or negative sentiment alone', () => {
    const fixture = setup([
      {
        ...ready,
        result: {
          ...ready.result!,
          critical_terms: ready.result!.critical_terms.map((mention) => ({
            ...mention,
            negated: true,
          })),
        },
      },
    ]);
    expect(fixture.nativeElement.querySelector('.priority-alert')).toBeNull();
    expect(fixture.nativeElement.querySelector('.priority-label')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Menção negada');
    expect(fixture.nativeElement.textContent).toContain('Negativo');
  });

  it('updates priority when another recording is selected without altering consent', () => {
    const fixture = setup([ready, { ...source, id: 'another' }]);
    fixture.componentInstance.consent.set(true);
    const files = fixture.nativeElement.querySelectorAll('.file');
    files[1].click();
    fixture.detectChanges();
    expect(fixture.componentInstance.selected()?.id).toBe('another');
    expect(fixture.nativeElement.querySelector('.priority-alert')).toBeNull();
    expect(fixture.componentInstance.consent()).toBe(true);
  });

  it('uploads the selected file without automatically sending it to Azure', () => {
    const fixture = setup([]);
    expect(fixture.nativeElement.querySelector('.library').open).toBe(true);
    const input = fixture.nativeElement.querySelector('input[type=file]') as HTMLInputElement;
    const file = new File(['wav data'], 'consulta.wav', { type: 'audio/wav' });
    Object.defineProperty(input, 'files', { value: [file] });
    input.dispatchEvent(new Event('change'));
    const upload = http.expectOne('/api/audios');
    expect(upload.request.method).toBe('POST');
    expect(upload.request.body.get('file')).toBe(file);
    upload.flush(source);
    http.expectNone('/api/audios/consulta/analyze');
    fixture.detectChanges();
    expect(fixture.componentInstance.selected()?.id).toBe('consulta');
    expect(fixture.nativeElement.querySelector('audio[controls]')).not.toBeNull();
  });

  it('starts Azure analysis automatically after conversion when authorization was given', () => {
    vi.useFakeTimers();
    const fixture = setup([]);
    fixture.componentInstance.consent.set(true);
    const input = fixture.nativeElement.querySelector('input[type=file]') as HTMLInputElement;
    const file = new File(['wav data'], 'consulta.wav', { type: 'audio/wav' });
    Object.defineProperty(input, 'files', { value: [file] });
    input.dispatchEvent(new Event('change'));
    http.expectOne('/api/audios').flush({
      ...source,
      status: 'importing',
      duration: 0,
      url: null,
      acoustic: null,
    });

    vi.advanceTimersByTime(1000);
    http.expectOne('/api/audios/consulta').flush(source);
    http.expectOne('/api/audios/consulta/analyze').flush({ ...source, status: 'queued' });
    expect(fixture.componentInstance.busy()).toBe(true);
    fixture.destroy();
  });

  it('requires authorization and displays real Azure sentiment, terms and timestamps', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.analyze();
    http.expectNone('/api/audios/consulta/analyze');
    component.consent.set(true);
    component.analyze();
    http.expectOne('/api/audios/consulta/analyze').flush(ready);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Negativo');
    expect(fixture.nativeElement.textContent).toContain('falta de ar');
    expect(fixture.nativeElement.textContent).toContain('Prioridade de revisão: alta');
    expect(fixture.nativeElement.textContent).toContain('92%');
    expect(fixture.nativeElement.textContent).toContain('1:01');
    component.seek(61);
    expect(component.player()?.nativeElement.currentTime).toBe(61);
    expect(component.activeSegment()).toBe(0);
    component.seek(2);
    expect(component.activeSegment()).toBe(-1);
  });

  it('preserves playback and transcription after a partial Azure Language failure', () => {
    const partial: ClinicalAudio = {
      ...ready,
      status: 'failed',
      error: 'Azure Language indisponível.',
      result: { ...ready.result!, language: undefined },
    };
    const fixture = setup([partial]);
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain(
      'Azure Language indisponível',
    );
    expect(fixture.nativeElement.textContent).toContain('Tenho falta de ar.');
    expect(fixture.nativeElement.textContent).not.toContain('Negativo');
    expect(fixture.nativeElement.querySelector('audio[controls]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.clinical .priority-alert')).not.toBeNull();
  });

  it('polls asynchronous processing and stops when the analysis finishes', () => {
    vi.useFakeTimers();
    const fixture = setup();
    fixture.componentInstance.consent.set(true);
    fixture.componentInstance.analyze();
    http.expectOne('/api/audios/consulta/analyze').flush({ ...source, status: 'queued' });
    vi.advanceTimersByTime(1000);
    http.expectOne('/api/audios/consulta').flush(ready);
    vi.advanceTimersByTime(3000);
    http.expectNone('/api/audios/consulta');
    expect(fixture.componentInstance.busy()).toBe(false);
    fixture.destroy();
  });

  it('cancels old polling when another consultation is selected or the page is destroyed', () => {
    vi.useFakeTimers();
    const fixture = setup([{ ...source, status: 'analyzing' }]);
    vi.advanceTimersByTime(1000);
    const old = http.expectOne('/api/audios/consulta');
    fixture.componentInstance.select({ ...source, id: 'another' });
    expect(old.cancelled).toBe(true);
    fixture.componentInstance.select({ ...source, status: 'analyzing' });
    fixture.destroy();
    vi.advanceTimersByTime(4000);
    http.expectNone('/api/audios/consulta');
  });

  it('reports unavailable backend without demonstration fallback', () => {
    const fixture = TestBed.createComponent(Voice);
    http.expectOne('/api/audios').flush(
      { detail: 'Servidor indisponível' },
      {
        status: 503,
        statusText: 'Unavailable',
      },
    );
    http
      .expectOne('/api/audios/configuration')
      .flush({ configured: false, message: 'Configure Azure.' });
    fixture.detectChanges();
    expect(fixture.componentInstance.audios()).toEqual([]);
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain(
      'Servidor indisponível',
    );
  });

  it('deletes the recording and its results', () => {
    const fixture = setup();
    fixture.componentInstance.deleteSelected();
    const request = http.expectOne('/api/audios/consulta');
    expect(request.request.method).toBe('DELETE');
    request.flush(null);
    expect(fixture.componentInstance.selected()).toBeNull();
    expect(fixture.componentInstance.audios()).toEqual([]);
  });
});
