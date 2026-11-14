import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Home } from './home';

describe('Home dashboard', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [Home], providers: [provideRouter([])] }));

  it('renders all module navigation and explicitly simulated telemetry descriptions', () => {
    const fixture = TestBed.createComponent(Home);
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelectorAll('article.module')).toHaveLength(3);
    expect([...element.querySelectorAll('a.cta')].map(link => link.getAttribute('href')))
      .toEqual(['/video', '/voice', '/telemetry']);
    expect(element.textContent).toContain('Simulação fictícia');
    expect(element.querySelector('img')?.getAttribute('alt')).toContain('fisioterapia');
  });

  it('toggles the illustrative incident table and its accessible expanded state', () => {
    const fixture = TestBed.createComponent(Home);
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;
    const button = element.querySelector<HTMLButtonElement>('button.incidents-head')!;
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(element.querySelectorAll('tbody tr')).toHaveLength(3);
    button.click();
    fixture.detectChanges();
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(element.querySelector('table')).toBeNull();
    button.click();
    fixture.detectChanges();
    expect(element.querySelectorAll('tbody tr')).toHaveLength(3);
  });
});
