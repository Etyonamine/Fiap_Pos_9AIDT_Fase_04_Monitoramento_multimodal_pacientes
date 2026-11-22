import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { SyntheticStream } from './synthetic-stream';

describe('SyntheticStream', () => {
  let http: HttpTestingController;
  const values = { heart_rate_bpm: 78, systolic_mmhg: 120, diastolic_mmhg: 80,
    spo2_percent: 97, medication: 'Medicamento sintético', dose: 10, unit: 'mg',
    expected_regimen: { dose: 10, unit: 'mg', status: 'active' },
    synthetic_note: 'Pessoa sintética relata cansaço.' };

  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      imports: [SyntheticStream],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('streams synthetic samples only as the bound session advances and shows delivery', () => {
    const fixture = TestBed.createComponent(SyntheticStream);
    fixture.componentRef.setInput('sessionId', 'session-1');
    fixture.componentRef.setInput('elapsed', 0);
    fixture.detectChanges();
    fixture.componentInstance.start();
    http.expectOne('/api/synthetic-stream/session-1').flush({
      session_id: 'session-1', samples: [], notice: 'Simulação sintética',
    });
    const first = http.expectOne('/api/synthetic-stream/session-1/samples');
    expect(first.request.body).toMatchObject({ timestamp: 0, scenario: 'stable' });
    first.flush({
      session_id: 'session-1', notice: 'Simulação sintética',
      samples: [{ sample_id: first.request.body.sample_id, timestamp: 0, values, events: [],
        media_matches: [], delivery_status: null, delivery_error: null }],
    });
    vi.advanceTimersByTime(5000);
    http.expectNone('/api/synthetic-stream/session-1/samples');
    http.expectOne('/api/synthetic-stream/session-1').flush({
      session_id: 'session-1', notice: 'Simulação sintética',
      samples: [{ sample_id: first.request.body.sample_id, timestamp: 0, values, events: [],
        media_matches: [], delivery_status: null, delivery_error: null }],
    });
    fixture.componentRef.setInput('elapsed', 10);
    fixture.detectChanges();
    vi.advanceTimersByTime(5000);
    const second = http.expectOne('/api/synthetic-stream/session-1/samples');
    expect(second.request.body).toMatchObject({ timestamp: 10, scenario: 'change' });
    second.flush({
      session_id: 'session-1', notice: 'Simulação sintética',
      samples: [{ sample_id: second.request.body.sample_id, timestamp: 10, values,
        events: [{ kind: 'threshold_crossing', message: 'Revisar sinal sintético.' }],
        media_matches: [{ id: 'incident-1', timestamp: 10, modalities: ['audio', 'image'] }],
        delivery_status: 'delivered', delivery_error: null }],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Revisar sinal sintético');
    expect(fixture.nativeElement.textContent).toContain('Nota sintética: Pessoa sintética relata cansaço.');
    expect(fixture.nativeElement.textContent).toContain('Referência sintética: 10 mg');
    expect(fixture.nativeElement.textContent).toContain('incidente(s) de imagem/fala');
    expect(fixture.nativeElement.textContent).toContain('webhook sintético local');
    fixture.componentInstance.stop();
    fixture.componentRef.setInput('elapsed', 20);
    fixture.detectChanges();
    vi.advanceTimersByTime(5000);
    http.expectNone('/api/synthetic-stream/session-1/samples');
  });

  it('sends an editable synthetic note and renders derived evolution without source text', () => {
    const fixture = TestBed.createComponent(SyntheticStream);
    fixture.componentRef.setInput('sessionId', 'session-1');
    fixture.componentRef.setInput('elapsed', 5);
    fixture.detectChanges();
    const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    textarea.value = 'Pessoa sintética relata cansaço.';
    textarea.dispatchEvent(new Event('input'));
    fixture.componentInstance.start();
    http.expectOne('/api/synthetic-stream/session-1').flush({
      session_id: 'session-1', samples: [], notice: 'Simulação sintética',
    });
    const request = http.expectOne('/api/synthetic-stream/session-1/samples');
    expect(request.request.body.note).toBe('Pessoa sintética relata cansaço.');
    request.flush({
      session_id: 'session-1', notice: 'Simulação sintética',
      samples: [{
        sample_id: request.request.body.sample_id, timestamp: 5,
        values: {
          ...values,
          synthetic_note: undefined,
          custom_note: true,
          note_evolution: {
            introduced: [{ term: 'cansaço', severity: 'warning' }],
            persisted: [], resolved: [],
            notice: 'Evolução derivada; não é diagnóstico.',
          },
        },
        events: [], media_matches: [], delivery_status: null, delivery_error: null,
      }],
    });
    fixture.detectChanges();
    const content = fixture.nativeElement.textContent as string;
    expect(content).toContain('Evolução textual derivada');
    expect(content).toContain('introduzidas: cansaço');
    expect(content).toContain('O texto original não foi persistido');
    expect(content).not.toContain('Nota sintética: Pessoa sintética');
    fixture.componentInstance.stop();
  });

  it('reports request failures and clears state on session changes', () => {
    const fixture = TestBed.createComponent(SyntheticStream);
    fixture.componentRef.setInput('sessionId', 'session-1');
    fixture.detectChanges();
    fixture.componentInstance.start();
    http.expectOne('/api/synthetic-stream/session-1').flush(
      { detail: 'Sessão encerrada.' }, { status: 409, statusText: 'Conflict' },
    );
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Sessão encerrada');
    expect(fixture.componentInstance.running()).toBe(false);
    fixture.componentInstance.noteDraft.set('Nota que não deve atravessar sessões.');
    fixture.componentRef.setInput('sessionId', 'session-2');
    fixture.detectChanges();
    expect(fixture.componentInstance.error()).toBe('');
    expect(fixture.componentInstance.busy()).toBe(false);
    expect(fixture.componentInstance.noteDraft()).toBe('');
  });

  it('shows a failed synthetic delivery and retries it without creating a new sample', () => {
    const fixture = TestBed.createComponent(SyntheticStream);
    fixture.componentRef.setInput('sessionId', 'session-1');
    fixture.detectChanges();
    fixture.componentInstance.refresh();
    const failed = {
      sample_id: 'sample-1', timestamp: 5, values: {
        ...values, synthetic_note: undefined, expected_regimen: undefined,
      },
      events: [{ kind: 'regimen_changed', message: 'Revisar prescrição.' }],
      media_matches: [], delivery_status: 'failed', delivery_error: 'Falha no receptor sintético.',
    };
    http.expectOne('/api/synthetic-stream/session-1').flush({
      session_id: 'session-1', notice: 'Simulação sintética', samples: [failed],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Falha no receptor sintético');
    fixture.nativeElement.querySelector('button:last-child')?.click();
    http.expectOne('/api/synthetic-stream/session-1/samples/sample-1/retry').flush({
      session_id: 'session-1', notice: 'Simulação sintética',
      samples: [{ ...failed, delivery_status: 'delivered', delivery_error: null }],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Recebido pelo webhook sintético local');
  });

  it('ignores a stale response after changing sessions and stops when closed', () => {
    const fixture = TestBed.createComponent(SyntheticStream);
    fixture.componentRef.setInput('sessionId', 'session-1');
    fixture.detectChanges();
    fixture.componentInstance.start();
    const oldRequest = http.expectOne('/api/synthetic-stream/session-1');
    fixture.componentRef.setInput('sessionId', 'session-2');
    fixture.detectChanges();
    oldRequest.flush({ session_id: 'session-1', samples: [], notice: 'antigo' });
    expect(fixture.componentInstance.result()).toBeNull();
    fixture.componentInstance.start();
    const next = http.expectOne('/api/synthetic-stream/session-2');
    fixture.componentRef.setInput('closed', true);
    fixture.detectChanges();
    next.flush({ session_id: 'session-2', samples: [], notice: 'novo' });
    expect(fixture.componentInstance.running()).toBe(false);
    http.expectNone('/api/synthetic-stream/session-2/samples');
  });
});
