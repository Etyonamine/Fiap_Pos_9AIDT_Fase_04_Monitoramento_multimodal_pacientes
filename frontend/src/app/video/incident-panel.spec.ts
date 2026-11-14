import { DATE_PIPE_DEFAULT_OPTIONS } from '@angular/common';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { IncidentPanel } from './incident-panel';
import { Incident, mergeIncidents } from './video-api';

const incident: Incident = {
  id: 'incident-1', session_id: 'session', video_id: 'bed', timestamp: 2,
  severity: 'critical', modalities: ['audio', 'image'], multimodal: true,
  status: 'confirmed', acknowledged: false, correlation_seconds: 10,
  created_at: '2026-01-02T03:04:00Z', updated_at: '2026-01-02T03:04:00Z',
  version: 2, merged_into: null, origin: 'recording', name: 'bed.mp4',
  evidence: [
    { id: 'image', session_id: 'session', video_id: 'bed', timestamp: 2,
      kind: 'Saída da cerca virtual', source: 'image', status: 'confirmed',
      created_at: '2026-01-02T03:04:00Z', updated_at: '2026-01-02T03:04:00Z',
      acknowledged_at: null, version: 1, text: null },
    { id: 'audio', session_id: 'session', video_id: 'bed', timestamp: 4,
      kind: 'Fala: socorro', source: 'audio', status: 'confirmed',
      created_at: '2026-01-02T03:04:00Z', updated_at: '2026-01-02T03:04:00Z',
      acknowledged_at: null, version: 1, text: 'Socorro, preciso de ajuda.' },
  ],
};

describe('Multimodal incident panel', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [IncidentPanel],
      providers: [provideHttpClient(), provideHttpClientTesting(),
        { provide: DATE_PIPE_DEFAULT_OPTIONS, useValue: { timezone: 'UTC' } }],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('shows a single incident with both timed evidences, transcript and replay navigation', () => {
    const fixture = TestBed.createComponent(IncidentPanel);
    fixture.componentRef.setInput('incidents', [incident]);
    fixture.componentRef.setInput('canSeek', true);
    const seek = vi.fn();
    fixture.componentInstance.seekEvidence.subscribe(seek);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelectorAll('article')).toHaveLength(1);
    expect(element.textContent).toContain('Incidente multimodal');
    expect(element.textContent).toContain('Saída da cerca virtual');
    expect(element.textContent).toContain('Socorro, preciso de ajuda.');
    expect(element.textContent).toContain('Aguardando registro');
    element.querySelector<HTMLButtonElement>('article button')!.click();
    expect(seek).toHaveBeenCalledWith(2);
    http.expectNone('/api/incidents');
  });

  it('keeps acknowledgement per evidence and uses newest alert versions without waiting for polling', () => {
    const fixture = TestBed.createComponent(IncidentPanel);
    const component = fixture.componentInstance;
    fixture.componentRef.setInput('incidents', [incident]);
    const recorded = incident.evidence.map(item => ({
      ...item, acknowledged_at: '2026-01-02T03:05:00Z', version: 2,
    }));
    fixture.componentRef.setInput('alerts', [recorded[0]]);
    fixture.detectChanges();
    expect(component.acknowledged(incident)).toBe(false);
    fixture.componentRef.setInput('alerts', recorded);
    fixture.detectChanges();
    expect(component.acknowledged(incident)).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('Ida ao atendimento registrada');
  });

  it('does not show merged tombstones as duplicate current incidents and labels provisional and withdrawn', () => {
    const fixture = TestBed.createComponent(IncidentPanel);
    fixture.componentRef.setInput('incidents', [
      { ...incident, status: 'provisional' },
      { ...incident, id: 'merged', merged_into: incident.id },
    ]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('article')).toHaveLength(1);
    expect(fixture.nativeElement.textContent).toContain('PROVISÓRIO');
    fixture.componentRef.setInput('incidents', [{ ...incident, status: 'retracted', multimodal: false, modalities: [] }]);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('RETIRADO');
    expect(fixture.nativeElement.textContent).toContain('Sem alerta ativo');
  });

  it('loads persistent cross-source history, pagination and immutable evidence audit on demand', () => {
    const fixture = TestBed.createComponent(IncidentPanel);
    const component = fixture.componentInstance;
    fixture.detectChanges();
    component.loadHistory();
    http.expectOne('/api/incidents').flush({ items: [incident], next_cursor: 4 });
    component.loadHistory(true);
    const camera = { ...incident, id: 'camera-incident', origin: 'camera', name: 'Câmera' };
    http.expectOne('/api/incidents?before=4').flush({ items: [camera], next_cursor: null });
    fixture.detectChanges();
    expect(component.history()).toHaveLength(2);
    expect(fixture.nativeElement.textContent).toContain('bed.mp4');
    expect(fixture.nativeElement.textContent).toContain('Câmera');
    component.loadAudit(incident.id);
    http.expectOne('/api/incidents/incident-1/history').flush({
      items: [{ id: 2, action: 'updated', created_at: incident.updated_at, payload: incident }],
      next_cursor: 2,
    });
    component.loadAudit(incident.id, true);
    http.expectOne('/api/incidents/incident-1/history?before=2').flush({
      items: [{ id: 1, action: 'created', created_at: incident.created_at, payload: { ...incident, version: 1 } }],
      next_cursor: null,
    });
    fixture.detectChanges();
    expect(component.audit()).toHaveLength(2);
    expect(fixture.nativeElement.textContent).toContain('Evidências desta versão');
    component.loadHistory();
    http.expectOne('/api/incidents').flush({ items: [], next_cursor: null });
    expect(component.history()).toEqual([]);
  });

  it('surfaces history errors and permits retry', () => {
    const fixture = TestBed.createComponent(IncidentPanel);
    fixture.componentInstance.loadHistory();
    http.expectOne('/api/incidents').flush({ detail: 'Banco indisponível.' }, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain('Banco indisponível.');
    expect(fixture.componentInstance.loading()).toBe(false);
    fixture.componentInstance.loadHistory();
    http.expectOne('/api/incidents').flush({ items: [], next_cursor: null });
    expect(fixture.componentInstance.error()).toBe('');
  });

  it('merges out-of-order image and audio snapshots by incident version, including retraction and merging', () => {
    const old = { ...incident, version: 1, multimodal: false };
    expect(mergeIncidents([incident], [old])).toEqual([incident]);
    const retracted = { ...incident, version: 3, multimodal: false, status: 'retracted' as const };
    expect(mergeIncidents([incident], [retracted], undefined)).toEqual([retracted]);
    const merged = { ...incident, version: 4, merged_into: 'another' };
    expect(mergeIncidents([retracted], [merged], [incident])).toEqual([merged]);
  });
});
