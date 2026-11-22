import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ClinicalDataPanel } from './clinical-data-panel';
import { ClinicalImport, MediaIncident, NotificationStatus } from './clinical-data-api';

const disabledNotifications: NotificationStatus = {
  enabled: false,
  configured: false,
  worker_running: false,
  message: 'Webhook desativado; nenhum alerta externo é enviado.',
  items: [],
};

const point = {
  recorded_at: '2026-11-18T13:00:00Z',
  patient_ref: 'imp-12345678-001',
  heart_rate_bpm: 78,
  systolic_mmhg: 120,
  diastolic_mmhg: 80,
  spo2_percent: 97,
};

const vitalImport: ClinicalImport = {
  id: '12345678',
  kind: 'vitals',
  name: 'vitals.csv',
  created_at: '2026-11-18T13:01:00Z',
  record_count: 1,
  patient_count: 1,
  points: [point],
  events: [{
    recorded_at: point.recorded_at,
    patient_ref: point.patient_ref,
    kind: 'threshold_crossing',
    field: 'heart_rate_bpm',
    message: 'Frequência cardíaca acima do limite demonstrativo.',
    priority: 'review',
  }],
  rules: { notice: 'Limites demonstrativos.' },
};

describe('ClinicalDataPanel', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ClinicalDataPanel],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
  });

  function setup(imports: ClinicalImport[] = [], incidents: MediaIncident[] = []) {
    const fixture = TestBed.createComponent(ClinicalDataPanel);
    fixture.detectChanges();
    http.expectOne('/api/notifications/status').flush(disabledNotifications);
    http.expectOne('/api/clinical-data/imports').flush(imports);
    http.expectOne('/api/incidents?limit=100').flush({ items: incidents, next_cursor: null });
    fixture.detectChanges();
    return fixture;
  }

  function fileChange(input: HTMLInputElement, file: File) {
    Object.defineProperty(input, 'files', { configurable: true, value: [file] });
    input.dispatchEvent(new Event('change'));
  }

  it('loads prior imports, maps a vital upload and displays a combined review timeline', () => {
    const incident: MediaIncident = {
      id: 'incident-1',
      created_at: '2026-11-18T13:02:00Z',
      timestamp: 2,
      modalities: ['image', 'audio'],
      status: 'active',
      evidence: [
        { source: 'image', kind: 'fence_exit', text: null, status: 'active' },
        { source: 'audio', kind: 'critical_term', text: 'Socorro', status: 'active' },
        { source: 'audio', kind: 'retracted', text: 'Retirada', status: 'retracted' },
      ],
    };
    const fixture = setup([vitalImport], [incident]);
    const input = fixture.nativeElement.querySelector('#vitals-file') as HTMLInputElement;
    const file = new File(['csv'], 'new-vitals.csv', { type: 'text/csv' });
    fileChange(input, file);

    const upload = http.expectOne('/api/clinical-data/vitals');
    expect(upload.request.method).toBe('POST');
    expect(upload.request.body.get('file')).toBe(file);
    upload.flush(vitalImport);
    http.expectOne('/api/notifications/status').flush(disabledNotifications);
    http.expectOne('/api/clinical-data/imports').flush([vitalImport]);
    http.expectOne('/api/incidents?limit=100').flush({ items: [incident], next_cursor: null });
    fixture.detectChanges();

    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('.clinical-data-heading')?.textContent).toContain(
      'Não inclua identificadores nos nomes dos arquivos.',
    );
    expect(element.querySelectorAll('.import-result')).toHaveLength(1);
    expect(element.querySelector('.import-result')?.textContent).toContain('1 evento(s)');
    expect(element.querySelector('.import-result')?.textContent).toContain('FC 78 bpm');
    expect(element.querySelector('.timeline-scroll')?.textContent).toContain('Frequência cardíaca');
    expect(element.querySelector('.timeline-scroll')?.textContent).toContain('Socorro');
    expect(element.querySelector('.timeline-scroll')?.textContent).not.toContain('Retirada');
    expect(element.querySelector('.timeline-scroll')?.textContent).toContain('imp-12345678-001');
  });

  it('distinguishes matching, divergent and missing prescription references', () => {
    const prescription: ClinicalImport = {
      ...vitalImport,
      kind: 'prescriptions',
      name: 'synthetic.json',
      points: undefined,
      records: [
        ...Array.from({ length: 18 }, () => ({
          recorded_at: point.recorded_at, patient_ref: point.patient_ref, medication: 'Sem plano',
          dose: 1, unit: 'mg', status: 'active' as const, route: 'oral', frequency: '',
        })),
        {
          recorded_at: point.recorded_at, patient_ref: point.patient_ref, medication: 'Medicamento A',
          dose: 20, unit: 'mg', status: 'active', route: 'oral', frequency: 'diária',
          expected_regimen: {
            dose: 20, unit: 'mg', status: 'active', route: 'oral', frequency: 'diária',
          },
          plan_comparison: {
            status: 'matches', compared_fields: ['dose', 'unit', 'status', 'route', 'frequency'],
            different_fields: [],
          },
        },
        {
          recorded_at: point.recorded_at, patient_ref: point.patient_ref, medication: 'Medicamento A',
          dose: 30, unit: 'mg', status: 'active', route: 'oral', frequency: '',
          expected_regimen: { dose: 20, unit: 'mg', status: 'active' },
          plan_comparison: {
            status: 'differs', compared_fields: ['dose', 'unit', 'status', 'route'],
            different_fields: ['dose'], missing_fields: ['route'],
          },
        },
        {
          recorded_at: point.recorded_at, patient_ref: point.patient_ref, medication: 'Medicamento B',
          dose: 1, unit: 'mg', status: 'active', route: 'oral', frequency: '',
          plan_comparison: { status: 'not_provided', compared_fields: [], different_fields: [] },
        },
        {
          recorded_at: point.recorded_at, patient_ref: point.patient_ref, medication: 'Medicamento C',
          dose: 1, unit: 'mg', status: 'active', route: '', frequency: '',
          expected_regimen: { dose: 1, unit: 'mg', status: 'active', route: 'oral' },
          plan_comparison: {
            status: 'incomplete', compared_fields: ['dose', 'unit', 'status', 'route'],
            different_fields: [], missing_fields: ['route'],
          },
        },
      ],
      events: [{
        recorded_at: point.recorded_at, patient_ref: point.patient_ref,
        kind: 'expected_regimen_change', message: 'Alteração prevista.',
        priority: 'information',
      }],
    };
    const fixture = setup([prescription]);
    const element: HTMLElement = fixture.nativeElement;
    expect(element.textContent).toContain('Referência: 20 mg');
    expect(element.textContent).toContain('Compatível nos campos informados: dose, unit, status, route, frequency');
    expect(element.textContent).toContain('via oral');
    expect(element.textContent).toContain('frequência diária');
    expect(element.textContent).toContain('Divergência nos campos: dose');
    expect(element.textContent).toContain('Dados observados ausentes: route');
    expect(element.textContent).toContain('Comparação incompleta; dados observados ausentes: route');
    expect(element.textContent).toContain('Sem referência explícita; esperado não avaliado');
    expect(element.textContent).toContain('Exibindo os últimos 20 registros');
    expect(element.querySelector('.timeline-scroll')?.textContent).toContain('Informativo');
  });

  it('requires cloud authorization for notes and posts consent with the selected file', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    const file = new File(['{}'], 'note.json', { type: 'application/json' });
    const input = fixture.nativeElement.querySelector('#note-file') as HTMLInputElement;
    fileChange(input, file);
    expect(component.error()).toContain('Marque a autorização');
    http.expectNone('/api/clinical-data/notes');

    const checkbox = fixture.nativeElement.querySelector('.consent input') as HTMLInputElement;
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(input.disabled).toBe(false);
    fileChange(input, file);

    const upload = http.expectOne('/api/clinical-data/notes');
    expect(upload.request.method).toBe('POST');
    expect(upload.request.body.get('file')).toBe(file);
    expect(upload.request.body.get('consent_to_cloud')).toBe('true');
    const note: ClinicalImport = {
      ...vitalImport,
      kind: 'notes',
      name: 'note.json',
      points: undefined,
      events: [],
      language: {
        provider: 'Azure AI Language',
        key_phrases: ['falta de ar'],
        key_phrase_mentions: [
          { term: 'falta de ar', severity: 'critical', negated: false, key_phrases: ['falta de ar'] },
          { term: 'dor no peito', severity: 'critical', negated: true, key_phrases: ['dor no peito'] },
        ],
        sentiment: {
          label: 'negative',
          scores: { positive: 0.01, neutral: 0.09, negative: 0.9 },
          aggregation: 'weighted',
        },
      },
      notice: 'Texto original não persistido.',
    };
    upload.flush(note);
    http.expectOne('/api/notifications/status').flush(disabledNotifications);
    http.expectOne('/api/clinical-data/imports').flush([note]);
    http.expectOne('/api/incidents?limit=100').flush({ items: [], next_cursor: null });
    fixture.detectChanges();
    expect(component.message()).toContain('não foi persistido');
    expect(fixture.nativeElement.textContent).toContain('Azure AI Language');
    expect(fixture.nativeElement.textContent).toContain('falta de ar');
    expect(fixture.nativeElement.textContent).toContain('menção não negada');
    expect(fixture.nativeElement.textContent).toContain('menção negada');
  });

  it('surfaces service errors and shows empty-history states', () => {
    const fixture = TestBed.createComponent(ClinicalDataPanel);
    fixture.detectChanges();
    http.expectOne('/api/notifications/status').flush(disabledNotifications);
    http.expectOne('/api/clinical-data/imports').flush(
      { detail: 'Banco temporariamente indisponível.' },
      { status: 503, statusText: 'Unavailable' },
    );
    http.expectOne('/api/incidents?limit=100');
    fixture.detectChanges();
    expect(fixture.componentInstance.error()).toContain('Banco temporariamente indisponível');
    expect(fixture.nativeElement.textContent).toContain(
      'Nenhum arquivo clínico foi importado nesta instalação.',
    );
    expect(fixture.nativeElement.textContent).toContain('Nenhum evento para revisão.');
  });

  it('requires FHIR authorization and shows missing values and warnings without fabricating data', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.importFhir();
    expect(component.error()).toContain('confirme a autorização');
    http.expectNone('/api/clinical-data/fhir');

    const patient = fixture.nativeElement.querySelector('#fhir-patient') as HTMLInputElement;
    patient.value = 'synthetic-fhir-1';
    patient.dispatchEvent(new Event('input'));
    const authorization = fixture.nativeElement.querySelectorAll('.consent input')[1] as HTMLInputElement;
    authorization.checked = true;
    authorization.dispatchEvent(new Event('change'));
    const kind = fixture.nativeElement.querySelector('#fhir-kind') as HTMLSelectElement;
    kind.value = 'prescriptions';
    kind.dispatchEvent(new Event('change'));
    expect(component.fhirKind()).toBe('prescriptions');
    kind.value = 'vitals';
    kind.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    const button = [...fixture.nativeElement.querySelectorAll('button')]
      .find((item: HTMLButtonElement) => item.textContent?.includes('Consultar FHIR')) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    button.click();
    const query = http.expectOne('/api/clinical-data/fhir');
    expect(query.request.body).toEqual({
      patient_id: 'synthetic-fhir-1', kind: 'vitals', authorized: true,
    });
    const partial: ClinicalImport = {
      ...vitalImport, source: 'FHIR R4', name: 'FHIR R4 · sinais vitais',
      points: [{ recorded_at: point.recorded_at, patient_ref: point.patient_ref, spo2_percent: 88 }],
      warnings: ['1 observação incompatível.'],
    };
    query.flush(partial);
    http.expectOne('/api/notifications/status').flush(disabledNotifications);
    http.expectOne('/api/clinical-data/imports').flush([partial]);
    http.expectOne('/api/incidents?limit=100').flush({ items: [], next_cursor: null });
    fixture.detectChanges();
    const result = fixture.nativeElement.querySelector('.import-result') as HTMLElement;
    expect(result.textContent).toContain('FC indisponível');
    expect(result.textContent).toContain('PA indisponível/indisponível');
    expect(result.textContent).toContain('SpO₂ 88%');
    expect(result.textContent).toContain('1 observação incompatível.');
    expect(component.fhirPatientId()).toBe('');
    expect(component.fhirAuthorized()).toBe(false);
  });

  it('reports notification failures and retries failed deliveries', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.refreshNotifications();
    http.expectOne('/api/notifications/status').flush(null, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();
    expect(component.notificationError()).toContain('Falha ao carregar notificações');

    const status: NotificationStatus = {
      enabled: true, configured: true, worker_running: false,
      message: 'Webhook habilitado.', items: [{
        id: 'delivery-1', source: 'audio', created_at: point.recorded_at, updated_at: point.recorded_at,
        status: 'failed', attempts: 5, last_error: 'Webhook retornou HTTP 503.',
        http_status: 503, delivered_at: null,
      }],
    };
    component.refreshNotifications();
    http.expectOne('/api/notifications/status').flush(status);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('processamento da fila não está ativo');
    expect(fixture.nativeElement.textContent).toContain('Webhook retornou HTTP 503');
    const retry = [...fixture.nativeElement.querySelectorAll('button')]
      .find((item: HTMLButtonElement) => item.textContent?.includes('Repetir entrega')) as HTMLButtonElement;
    retry.click();
    http.expectOne('/api/notifications/delivery-1/retry').flush({ status: 'pending' });
    http.expectOne('/api/notifications/status').flush({
      ...status, worker_running: true, items: [{ ...status.items[0], status: 'pending', attempts: 0 }],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Pendente');
    expect(fixture.nativeElement.textContent).not.toContain('processamento da fila não está ativo');
  });

  it('surfaces FHIR and retry errors and permits trying again', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.fhirPatientId.set('synthetic-patient');
    component.fhirAuthorized.set(true);
    component.importFhir();
    expect(component.busy()).toBe(true);
    http.expectOne('/api/clinical-data/fhir').flush(
      { detail: 'FHIR não configurado.' }, { status: 503, statusText: 'Unavailable' },
    );
    expect(component.error()).toContain('FHIR não configurado.');
    expect(component.busy()).toBe(false);
    expect(component.fhirPatientId()).toBe('synthetic-patient');

    component.retryNotification('delivery-1');
    component.retryNotification('delivery-2');
    http.expectNone('/api/notifications/delivery-2/retry');
    http.expectOne('/api/notifications/delivery-1/retry').flush(
      { detail: 'Entrega indisponível.' }, { status: 409, statusText: 'Conflict' },
    );
    expect(component.notificationError()).toContain('Entrega indisponível.');
    expect(component.retrying()).toBe('');
  });
});
