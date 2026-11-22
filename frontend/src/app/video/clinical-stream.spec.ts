import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { ClinicalStream } from './clinical-stream';

describe('ClinicalStream', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      imports: [ClinicalStream],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('polls the active media session and displays source data, media match, and delivery state', () => {
    const fixture = TestBed.createComponent(ClinicalStream);
    fixture.componentRef.setInput('sessionId', 'session-1');
    fixture.componentRef.setInput('active', true);
    fixture.componentRef.setInput('closed', false);
    fixture.detectChanges();
    vi.advanceTimersByTime(0);

    http.expectOne('/api/clinical-stream/session-1').flush({
      session_id: 'session-1',
      notice: 'Review notice.',
      samples: [{
        sample_id: 'sample-1',
        source_id: 'case-001',
        recorded_at: '2026-11-22T00:00:00Z',
        elapsed_seconds: 10,
        vitals: { heart_rate_bpm: 132, spo2_percent: 88 },
        prescriptions: [],
        events: [{
          source: 'vitals',
          kind: 'threshold_crossing',
          field: 'heart_rate_bpm',
          message: 'Revisar sinais.',
          delivery_id: 'delivery-1',
          delivery: {
            status: 'delivered',
            last_error: null,
            http_status: 202,
            attempts: 1,
            delivered_at: '2026-11-22T00:00:01Z',
          },
        }],
        media_matches: [{ timestamp: 9.5, modalities: ['audio', 'image'] }],
      }],
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('FC 132 bpm');
    expect(fixture.nativeElement.textContent).toContain('SpO₂ 88%');
    expect(fixture.nativeElement.textContent).toContain('audio + image');
    expect(fixture.nativeElement.textContent).toContain('Aceito pelo destino');
    expect(fixture.nativeElement.textContent).toContain('Review notice.');
    fixture.destroy();
  });

  it('does not request clinical samples without an active media session', () => {
    const fixture = TestBed.createComponent(ClinicalStream);
    fixture.componentRef.setInput('sessionId', 'session-1');
    fixture.componentRef.setInput('active', false);
    fixture.componentRef.setInput('closed', false);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Inicie uma sessão');
    http.expectNone('/api/clinical-stream/session-1');
    fixture.destroy();
  });

  it('shows prescription review, empty media matches, webhook failures, and empty events', () => {
    const fixture = TestBed.createComponent(ClinicalStream);
    fixture.componentRef.setInput('sessionId', 'session-1');
    fixture.componentRef.setInput('active', true);
    fixture.componentRef.setInput('closed', false);
    fixture.detectChanges();
    vi.advanceTimersByTime(0);

    http.expectOne('/api/clinical-stream/session-1').flush({
      session_id: 'session-1',
      notice: 'Review notice.',
      samples: [{
        sample_id: 'sample-1',
        source_id: 'case-001',
        recorded_at: '2026-11-22T00:00:00Z',
        elapsed_seconds: 10,
        vitals: {},
        prescriptions: [{
          medication: 'Synthetic medication',
          dose: 5,
          unit: 'mg',
          status: 'discontinued',
        }],
        events: [{
          source: 'prescriptions',
          kind: 'regimen_changed',
          message: 'Revisar prescrição.',
          delivery_id: 'delivery-1',
          delivery: {
            status: 'failed',
            last_error: 'Destino indisponível.',
            http_status: 503,
            attempts: 5,
            delivered_at: null,
          },
        }],
        media_matches: [],
      }, {
        sample_id: 'sample-2',
        source_id: 'case-002',
        recorded_at: '2026-11-22T00:01:00Z',
        elapsed_seconds: 20,
        vitals: {},
        prescriptions: [],
        events: [],
        media_matches: [],
      }],
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Prescrição interrompida');
    expect(fixture.nativeElement.textContent).toContain('Synthetic medication, 5 mg');
    expect(fixture.nativeElement.textContent).toContain('Destino indisponível.');
    expect(fixture.nativeElement.textContent).toContain('Nenhuma regra de revisão');
    expect(fixture.nativeElement.textContent).not.toContain('Correspondência temporal');
    fixture.destroy();
  });

  it('shows explicit polling errors from the clinical stream API', () => {
    const fixture = TestBed.createComponent(ClinicalStream);
    fixture.componentRef.setInput('sessionId', 'session-1');
    fixture.componentRef.setInput('active', true);
    fixture.componentRef.setInput('closed', false);
    fixture.detectChanges();
    vi.advanceTimersByTime(0);

    http.expectOne('/api/clinical-stream/session-1').flush(
      { detail: 'Clinical source unavailable.' },
      { status: 503, statusText: 'Unavailable' },
    );
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain(
      'Clinical source unavailable.',
    );
    fixture.destroy();
  });
});
