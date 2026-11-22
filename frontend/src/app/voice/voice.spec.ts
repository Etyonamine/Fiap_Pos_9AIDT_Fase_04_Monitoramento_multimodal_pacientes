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
    active_window_ratio: 0.6,
    quiet_period_count: 2,
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
      key_phrase_mentions: [{
        term: 'falta de ar', severity: 'critical', negated: false,
        key_phrases: ['falta de ar'],
      }],
      sentiment: {
        label: 'negative',
        scores: { positive: 0.01, neutral: 0.09, negative: 0.9 },
        chunks: [],
        aggregation: 'Média ponderada dos trechos.',
      },
    },
    delivery: {
      recognized_words: 5,
      recognized_speech_seconds: 4,
      estimated_words_per_minute: 75,
      inter_segment_pauses_over_half_second: 1,
      longest_inter_segment_pause_seconds: 1,
      notice: 'Estimativa descritiva baseada em transcrição; não mede estado clínico.',
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
    details[1].open = true;
    fixture.detectChanges();
    expect(details[1].textContent).toContain('Palavras por minuto estimadas');
    expect(details[1].textContent).toContain('75');
    expect(details[1].textContent).toContain('não mede estado clínico');
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
          language: {
            ...ready.result!.language!,
            key_phrase_mentions: [{
              term: 'falta de ar', severity: 'critical', negated: true,
              key_phrases: ['falta de ar'],
            }],
          },
        },
      },
    ]);
    expect(fixture.nativeElement.querySelector('.priority-alert')).toBeNull();
    expect(fixture.nativeElement.querySelector('.priority-label')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Menção negada');
    expect(fixture.nativeElement.textContent).toContain('menção negada');
    expect(fixture.nativeElement.textContent).toContain('Negativo');
  });

  it('identifies simulated transcription and never presents tones as recognized speech', () => {
    const fixture = setup([{
      ...ready,
      result: {
        ...ready.result!,
        transcription: {
          ...ready.result!.transcription, provider: 'Synthetic E2E', synthetic: true,
        },
      },
    }]);
    expect(fixture.nativeElement.textContent).toContain('SIMULAÇÃO: a transcrição');
    expect(fixture.nativeElement.textContent).toContain('não houve reconhecimento pelo Azure');
    expect(fixture.nativeElement.textContent).toContain('tons, não fala');
  });

  it('labels empty acoustic findings and unavailable delivery estimates explicitly', () => {
    const fixture = setup([{
      ...ready,
      acoustic: { ...source.acoustic!, indicators: [], energy_change_db: -6.2 },
      result: {
        ...ready.result!,
        language: undefined,
        delivery: {
          ...ready.result!.delivery!,
          estimated_words_per_minute: null,
        },
      },
    }]);
    const element: HTMLElement = fixture.nativeElement;
    const details = element.querySelectorAll<HTMLDetailsElement>('.supplementary details');
    details[1].open = true;
    fixture.detectChanges();
    expect(details[1].textContent).toContain('Nenhum limiar acústico exploratório');
    expect(details[1].textContent).toContain('Não mensurável');
    expect(details[1].textContent).toContain('-6.2 dB');
  });

  it.each([
    ['available', 'Cruzamentos por zero nas janelas ativas'],
    ['clipped', 'Comparação indisponível: a gravação apresenta saturação'],
    ['insufficient_audio', 'Comparação indisponível: são necessários 30 segundos'],
  ] as const)('shows experimental acoustic comparison: %s', (status, expected) => {
    const fixture = setup([{
      ...source,
      acoustic: {
        ...source.acoustic!,
        experimental_comparison: {
          status, initial_zero_crossing_rate: 0.02, final_zero_crossing_rate: 0.05,
          difference: 0.03, notice: 'Não identifica condições clínicas.',
        },
      },
    }]);
    expect(fixture.nativeElement.textContent).toContain(expected);
    expect(fixture.nativeElement.textContent).toContain('Não identifica condições clínicas.');
  });

  it('compares speech acoustic features with an operator-selected recording', () => {
    const baseline = { ...ready, id: 'baseline', name: 'referencia.wav' };
    const fixture = setup([{ ...ready, id: 'current' }, baseline]);
    const element: HTMLElement = fixture.nativeElement;
    const acousticDetails = element.querySelectorAll<HTMLDetailsElement>(
      '.supplementary details',
    )[1];
    acousticDetails.open = true;
    fixture.detectChanges();

    const reference = fixture.nativeElement.querySelector(
      'select[aria-label="Gravação de referência"]',
    ) as HTMLSelectElement;
    reference.value = 'baseline';
    reference.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    const compareButton = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.textContent?.includes('Comparar características da fala'));
    compareButton?.click();
    fixture.detectChanges();

    const request = http.expectOne('/api/audios/current/compare/baseline');
    expect(request.request.method).toBe('POST');
    request.flush({
      status: 'available',
      current: {
        status: 'available', speech_windows: 5, median_f0_hz: 280,
        f0_range_hz: 12, median_rms_dbfs: -15, median_zero_crossing_rate: 0.04,
        notice: 'Indicador exploratório.',
      },
      reference: {
        status: 'available', speech_windows: 5, median_f0_hz: 180,
        f0_range_hz: 10, median_rms_dbfs: -14, median_zero_crossing_rate: 0.03,
        notice: 'Indicador exploratório.',
      },
      differences: {
        median_f0_percent: 55.6, f0_range_percent: 20,
        median_rms_db: -1, zero_crossing_rate_percent: 33.3,
      },
      changed_features: ['median_f0', 'zero_crossing_rate'],
      notice: 'Não é diagnóstico.',
      review: {
        status: 'combined_evidence',
        changed_features: ['median_f0', 'zero_crossing_rate'],
        reported_mentions: [{ term: 'falta de ar', severity: 'critical' }],
        notice: 'Evidências independentes; não demonstra causalidade.',
      },
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Diferenças acima dos limiares exploratórios');
    expect(fixture.nativeElement.textContent).toContain('Pitch mediano');
    expect(fixture.nativeElement.textContent).toContain('Não é diagnóstico.');
    expect(fixture.nativeElement.textContent).toContain('Diferença acústica e menção na transcrição');
    expect(fixture.nativeElement.textContent).toContain('Menção na transcrição: falta de ar');
    expect(fixture.nativeElement.textContent).toContain('não demonstra causalidade');
  });

  it.each([
    ['acoustic_change_only', 'Diferença acústica sem menção não negada'],
    ['reported_mention_only', 'Menção na transcrição sem diferença'],
    ['insufficient_acoustic_data', 'Dados acústicos insuficientes'],
    ['no_flags', 'Nenhum dos sinais exploratórios'],
  ] as const)('explains joint voice-review status: %s', (status, expected) => {
    const fixture = setup([{ ...ready, id: 'current' }, { ...ready, id: 'baseline' }]);
    fixture.componentInstance.voiceComparison.set({
      status: status === 'insufficient_acoustic_data' ? 'insufficient_speech' : 'available',
      current: { status: 'available', speech_windows: 5, notice: 'Experimental.' },
      reference: { status: 'available', speech_windows: 5, notice: 'Experimental.' },
      changed_features: [],
      notice: 'Não é diagnóstico.',
      review: { status, changed_features: [], reported_mentions: [], notice: 'Não é diagnóstico.' },
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain(expected);
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

  it('requires authorization to select or upload a file and explains why', () => {
    const fixture = setup([]);
    expect(fixture.nativeElement.querySelector('.library').open).toBe(true);
    const input = fixture.nativeElement.querySelector('input[type=file]') as HTMLInputElement;
    const control = fixture.nativeElement.querySelector('.import-button') as HTMLElement;
    expect(input.disabled).toBe(true);
    expect(control.getAttribute('aria-describedby')).toBe('import-consent-help');
    expect(control.tabIndex).toBe(0);
    expect(control.querySelector('.import-tooltip')?.textContent).toContain('Marque a autorização');
    const file = new File(['wav data'], 'consulta.wav', { type: 'audio/wav' });
    Object.defineProperty(input, 'files', { value: [file] });
    input.dispatchEvent(new Event('change'));
    http.expectNone('/api/audios');

    const checkbox = fixture.nativeElement.querySelector('input[type=checkbox]') as HTMLInputElement;
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(input.disabled).toBe(false);
    expect(control.querySelector('.import-tooltip')).toBeNull();
    input.dispatchEvent(new Event('change'));
    const upload = http.expectOne('/api/audios');
    expect(upload.request.method).toBe('POST');
    expect(upload.request.body.get('file')).toBe(file);
    fixture.detectChanges();
    expect(input.disabled).toBe(true);
    upload.flush(source);
    http.expectOne('/api/audios/consulta/analyze').flush({ ...source, status: 'queued' });
    fixture.destroy();
  });

  it('does not start Azure analysis if authorization is withdrawn during conversion', () => {
    vi.useFakeTimers();
    const fixture = setup([]);
    fixture.componentInstance.consent.set(true);
    const input = fixture.nativeElement.querySelector('input[type=file]') as HTMLInputElement;
    Object.defineProperty(input, 'files', { value: [new File(['wav'], 'consulta.wav')] });
    input.dispatchEvent(new Event('change'));
    http.expectOne('/api/audios').flush({
      ...source, status: 'importing', duration: 0, url: null, acoustic: null,
    });
    fixture.componentInstance.consent.set(false);
    vi.advanceTimersByTime(1000);
    http.expectOne('/api/audios/consulta').flush(source);
    http.expectNone('/api/audios/consulta/analyze');
    expect(fixture.componentInstance.selected()?.status).toBe('uploaded');
    fixture.destroy();
  });

  it('summarizes selected results without implying absent findings mean no risk', () => {
    const fixture = setup([ready, source]);
    const summary = () => fixture.nativeElement.querySelector('.overview').textContent as string;
    expect(summary()).toContain('consulta.wav');
    expect(summary()).toContain('Prioridade de revisão: alta');
    expect(summary()).toContain('indicadores acústicos');
    expect(summary()).toContain('não envia alertas');
    fixture.componentInstance.select({ ...ready, id: 'sem-termos', result: { ...ready.result!, critical_terms: [] } });
    fixture.detectChanges();
    expect(summary()).toContain('isso não exclui risco clínico');
    expect(summary()).not.toContain('Prioridade de revisão: alta');
    fixture.componentInstance.select(source);
    fixture.detectChanges();
    expect(summary()).toContain('ainda não disponível');
    expect(summary()).not.toContain('Prioridade de revisão: alta');
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

  it('wires analyze, transcript seek, and media seeked events', () => {
    const fixture = setup([ready]);
    const component = fixture.componentInstance;
    component.consent.set(true);
    fixture.detectChanges();

    fixture.nativeElement.querySelector('.primary').click();
    const analysis = http.expectOne('/api/audios/consulta/analyze');
    expect(analysis.request.method).toBe('POST');
    analysis.flush(ready);
    fixture.detectChanges();

    const player = fixture.nativeElement.querySelector('audio') as HTMLAudioElement;
    const seek = fixture.nativeElement.querySelector(
      'button[aria-label="Ir para 1:01"]',
    ) as HTMLButtonElement;
    seek.click();
    expect(component.currentTime()).toBe(61);

    player.currentTime = 63;
    player.dispatchEvent(new Event('seeked'));
    fixture.detectChanges();
    expect(component.currentTime()).toBe(63);
    expect(component.activeSegment()).toBe(-1);
    fixture.destroy();
  });

  it('shows empty language terms and both comparison fallback states', () => {
    const current = {
      ...ready,
      result: {
        ...ready.result!,
        language: { ...ready.result!.language!, key_phrases: [] },
      },
    };
    const fixture = setup([current, { ...ready, id: 'baseline' }]);
    const element: HTMLElement = fixture.nativeElement;
    const detailPanels = element.querySelectorAll<HTMLDetailsElement>('.supplementary details');
    detailPanels[0].open = true;
    detailPanels[1].open = true;
    fixture.detectChanges();
    expect(element.textContent).toContain('Nenhum termo-chave extraído.');

    const reference = element.querySelector(
      'select[aria-label="Gravação de referência"]',
    ) as HTMLSelectElement;
    reference.value = 'baseline';
    reference.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    const compareButton = Array.from(
      element.querySelectorAll('button') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.textContent?.includes('Comparar características da fala'))!;

    compareButton.click();
    http.expectOne('/api/audios/consulta/compare/baseline').flush({
      status: 'available',
      current: { status: 'available' },
      reference: { status: 'available' },
      differences: {
        median_f0_percent: 2, f0_range_percent: 3,
        median_rms_db: 1, zero_crossing_rate_percent: 4,
      },
      changed_features: [],
      notice: 'No exploratory difference.',
    });
    fixture.detectChanges();
    expect(element.textContent).toContain('Nenhuma diferença ultrapassou os limiares');

    compareButton.click();
    http.expectOne('/api/audios/consulta/compare/baseline').flush({
      status: 'insufficient_speech',
      current: { status: 'insufficient_speech' },
      reference: { status: 'insufficient_speech' },
      changed_features: [],
      notice: 'Insufficient synthetic speech.',
    });
    fixture.detectChanges();
    expect(element.textContent).toContain('fala reconhecida insuficiente');
    expect(element.textContent).toContain('Insufficient synthetic speech.');
    fixture.destroy();
  });
});
