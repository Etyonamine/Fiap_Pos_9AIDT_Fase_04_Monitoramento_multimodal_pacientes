import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Telemetry } from './telemetry';

describe('Telemetry clinical simulation', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [Telemetry],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    vi.useFakeTimers();
  });

  afterEach(() => {
    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  function setup() {
    const fixture = TestBed.createComponent(Telemetry);
    fixture.detectChanges();
    return fixture;
  }

  it('keeps stable data alert-free and retains only eight recent samples', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.start();
    vi.advanceTimersByTime(50000);
    expect(component.current().step).toBe(10);
    expect(component.samples().map((sample) => sample.step)).toEqual([3, 4, 5, 6, 7, 8, 9, 10]);
    expect(component.alerts()).toEqual([]);
    fixture.destroy();
  });

  it('records generation dates, preserves them on pause and displays the timestamp column', () => {
    vi.setSystemTime(new Date('2026-11-13T01:00:00Z'));
    const fixture = setup();
    const component = fixture.componentInstance;
    const initialTime = Date.now();
    expect(component.current().recordedAt).toBe(initialTime);
    component.start();
    vi.advanceTimersByTime(5000);
    expect(component.current().recordedAt).toBe(initialTime + 5000);
    component.pause();
    vi.advanceTimersByTime(20000);
    expect(component.current().recordedAt).toBe(initialTime + 5000);
    component.start();
    vi.advanceTimersByTime(5000);
    expect(component.current().recordedAt).toBe(initialTime + 30000);
    expect(component.elapsedSeconds()).toBe(10);
    fixture.detectChanges();
    const list: HTMLElement = fixture.nativeElement.querySelector('.samples-list');
    expect(list.tabIndex).toBe(0);
    const headers = [...list.querySelectorAll('th')].map((header) => header.textContent?.trim());
    expect(headers).toEqual(['Amostra · tempo (s)', 'Data e hora', 'FC (bpm)', 'PA (mmHg)', 'SpO₂ (%)']);
    const lastRow = list.querySelector('tbody tr:last-child')!;
    expect(lastRow.children[0].textContent).toContain('2 · 10 s');
    expect(lastRow.children[1].textContent).toMatch(/\d{2}\/11\/2026 \d{2}:\d{2}:30/);
    component.reset();
    expect(component.current().recordedAt).toBe(Date.now());
    expect(component.samples()).toHaveLength(1);
    fixture.destroy();
  });

  it('detects each simulated vital crossing and does not repeat sustained alerts', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    const select: HTMLSelectElement = fixture.nativeElement.querySelector('#scenario');
    select.value = 'vitals';
    select.dispatchEvent(new Event('change'));
    component.start();
    vi.advanceTimersByTime(5000);
    expect(component.alerts()).toHaveLength(0);
    vi.advanceTimersByTime(5000);
    fixture.detectChanges();
    expect(component.current()).toEqual({ step: 2, recordedAt: Date.now(), heartRate: 128, systolic: 185, diastolic: 112, oxygen: 88 });
    expect(component.alerts()).toHaveLength(3);
    expect(fixture.nativeElement.textContent).toContain('Frequência cardíaca acima');
    vi.advanceTimersByTime(15000);
    expect(component.alerts()).toHaveLength(3);
    fixture.destroy();
  });

  it('plots only real simulated samples using fixed scales and resets the trends', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    expect(component.trends().heartRate).toBe('4,28.4');
    expect(Number(component.trends().oxygen.split(',')[1])).toBeCloseTo(4.8);
    expect(fixture.nativeElement.querySelectorAll('.trend-dot')).toHaveLength(4);
    const select: HTMLSelectElement = fixture.nativeElement.querySelector('#scenario');
    select.value = 'vitals';
    select.dispatchEvent(new Event('change'));
    component.start();
    vi.advanceTimersByTime(10000);
    fixture.detectChanges();
    const heart = fixture.nativeElement.querySelector('polyline.heart').getAttribute('points').split(' ');
    expect(heart).toHaveLength(3);
    expect(Number(heart[2].split(',')[1])).toBeCloseTo(18.4);
    expect(fixture.nativeElement.querySelectorAll('.trend-dot')).toHaveLength(12);
    expect(fixture.nativeElement.textContent).toContain('não são ECG');
    component.reset();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.trend-dot')).toHaveLength(4);
    expect(component.trends().heartRate).toBe('4,28.4');
    fixture.destroy();
  });

  it('compares the fictitious prescription and supports the combined scenario', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    const select: HTMLSelectElement = fixture.nativeElement.querySelector('#scenario');
    select.value = 'prescription';
    select.dispatchEvent(new Event('change'));
    component.start();
    vi.advanceTimersByTime(10000);
    expect(component.doseChanged()).toBe(true);
    expect(component.alerts()).toHaveLength(1);
    expect(component.alerts()[0].message).toContain('10 para 30 mg');
    select.value = 'combined';
    select.dispatchEvent(new Event('change'));
    expect(component.running()).toBe(false);
    expect(component.current().step).toBe(0);
    expect(component.alerts()).toEqual([]);
    component.start();
    vi.advanceTimersByTime(10000);
    expect(component.alerts()).toHaveLength(4);
    fixture.destroy();
  });

  it('alerts at 30 simulated seconds and ends at 40 without repeating alerts', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    const select: HTMLSelectElement = fixture.nativeElement.querySelector('#scenario');
    select.value = 'sudden-deterioration';
    select.dispatchEvent(new Event('change'));
    component.start();
    vi.advanceTimersByTime(29999);
    expect(component.elapsedSeconds()).toBe(25);
    expect(component.alerts()).toHaveLength(0);
    expect(component.current().oxygen).toBe(98);
    vi.advanceTimersByTime(1);
    fixture.detectChanges();
    expect(component.elapsedSeconds()).toBe(30);
    expect(component.current()).toEqual({ step: 6, recordedAt: Date.now(), heartRate: 128, systolic: 185, diastolic: 112, oxygen: 88 });
    expect(component.alerts()).toHaveLength(3);
    expect(component.alerts().every((alert) => alert.step === 6)).toBe(true);
    expect(fixture.nativeElement.querySelectorAll('.simulation-alerts li')).toHaveLength(3);
    vi.advanceTimersByTime(9999);
    expect(component.elapsedSeconds()).toBe(35);
    expect(component.running()).toBe(true);
    vi.advanceTimersByTime(1);
    fixture.detectChanges();
    expect(component.elapsedSeconds()).toBe(40);
    expect(component.running()).toBe(false);
    expect(component.completed()).toBe(true);
    expect(component.alerts()).toHaveLength(3);
    expect(fixture.nativeElement.querySelector('.control-actions .primary').disabled).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('Simulação concluída');
    component.start();
    vi.advanceTimersByTime(20000);
    expect(component.elapsedSeconds()).toBe(40);
    component.reset();
    expect(component.elapsedSeconds()).toBe(0);
    expect(component.completed()).toBe(false);
    expect(component.alerts()).toHaveLength(0);
    component.start();
    vi.advanceTimersByTime(30000);
    expect(component.alerts()).toHaveLength(3);
    fixture.destroy();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('preserves the sudden deterioration timeline across pauses and scenario changes', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    const select: HTMLSelectElement = fixture.nativeElement.querySelector('#scenario');
    select.value = 'sudden-deterioration';
    select.dispatchEvent(new Event('change'));
    component.start();
    vi.advanceTimersByTime(25000);
    component.pause();
    vi.advanceTimersByTime(20000);
    expect(component.elapsedSeconds()).toBe(25);
    expect(component.alerts()).toHaveLength(0);
    component.start();
    vi.advanceTimersByTime(5000);
    expect(component.elapsedSeconds()).toBe(30);
    expect(component.alerts()).toHaveLength(3);
    select.value = 'stable';
    select.dispatchEvent(new Event('change'));
    expect(component.elapsedSeconds()).toBe(0);
    expect(component.running()).toBe(false);
    expect(component.completed()).toBe(false);
    expect(component.alerts()).toEqual([]);
    component.start();
    vi.advanceTimersByTime(45000);
    expect(component.elapsedSeconds()).toBe(45);
    expect(component.running()).toBe(true);
    fixture.destroy();
  });

  it('pauses, resumes without advancing while paused, and resets', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    component.start();
    vi.advanceTimersByTime(5000);
    component.pause();
    vi.advanceTimersByTime(15000);
    expect(component.current().step).toBe(1);
    expect(component.running()).toBe(false);
    component.start();
    vi.advanceTimersByTime(5000);
    expect(component.current().step).toBe(2);
    component.reset();
    vi.advanceTimersByTime(5000);
    expect(component.current().step).toBe(0);
    expect(component.running()).toBe(false);
    fixture.destroy();
    expect(vi.getTimerCount()).toBe(0);
  });
});
