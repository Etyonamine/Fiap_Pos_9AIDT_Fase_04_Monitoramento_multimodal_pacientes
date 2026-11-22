import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test, expect, type Page } from '@playwright/test';

const temporaryDirectory = mkdtempSync(path.join(os.tmpdir(), 'ytos-e2e-'));
const bedVideo = path.join(temporaryDirectory, 'bed-e2e.mp4');
const physioVideo = path.join(temporaryDirectory, 'fisio-e2e.mp4');
const consultation = path.join(temporaryDirectory, 'consult-e2e.wav');

function ffmpeg(args: string[]) {
  const result = spawnSync('ffmpeg', ['-nostdin', '-hide_banner', '-loglevel', 'error', '-y', ...args], {
    encoding: 'utf8',
    timeout: 30_000,
  });
  if (result.error || result.status !== 0) {
    throw new Error(`Falha ao criar mídia E2E sintética com FFmpeg: ${result.stderr || result.error}`);
  }
}

test.beforeAll(() => {
  ffmpeg([
    '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=25',
    '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000',
    '-t', '6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
    '-shortest', bedVideo,
  ]);
  ffmpeg([
    '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=25', '-t', '2',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-an', physioVideo,
  ]);
  ffmpeg([
    '-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=16000', '-t', '2',
    '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', consultation,
  ]);
});

test.afterAll(() => {
  rmSync(temporaryDirectory, { recursive: true, force: true });
});

async function uploadVideo(page: Page, file: string) {
  await page.locator('input[type="file"][accept=".mp4,.avi,.mov,.webm"]').setInputFiles(file);
}

test('real browser uploads a bed video, correlates played image and fake Speech, acknowledges and opens persisted unified history', async ({ page }) => {
  await page.goto('/telemetry');
  await expect(page.getByRole('heading', { name: 'Telemetria e anomalias' })).toBeVisible();
  await uploadVideo(page, bedVideo);
  const recording = page.getByRole('button', { name: /bed-e2e\.mp4/ });
  await expect(recording).toContainText('Pronto', { timeout: 30_000 });
  await recording.click();

  const player = page.locator('video[aria-label="Gravação analisada com controles de reprodução"]');
  await expect(player).toBeVisible();
  await player.evaluate(async (element: HTMLVideoElement) => {
    element.currentTime = 0;
    await element.play();
  });

  const incident = page.locator('app-incident-panel article.multimodal');
  await expect(incident).toContainText('Saída da cerca virtual', { timeout: 30_000 });
  await expect(incident).toContainText('Estou com falta de ar.', { timeout: 30_000 });
  await expect(incident).toContainText(/imagem \+ fala/i);

  await expect.poll(async () => {
    const response = await page.request.get('/api/notifications/status');
    const status = await response.json();
    return status.items.some((item: { status: string }) => item.status === 'delivered');
  }, { timeout: 15_000 }).toBe(true);
  await page.getByRole('button', { name: 'Atualizar notificações' }).click();
  await expect(page.locator('.notification-status')).toContainText('Aceita pelo destino');

  await page.getByRole('button', { name: /Ir ao atendimento/ }).first().click();
  await expect(incident).toContainText('Ida registrada em', { timeout: 10_000 });
  await page.getByRole('button', { name: 'Consultar / atualizar histórico unificado' }).click();
  const history = page.locator('app-incident-panel').getByRole('heading', {
    name: 'Histórico unificado · câmera e gravações',
  });
  await expect(history).toBeVisible();
  const savedIncident = page.locator('app-incident-panel details summary')
    .filter({ hasText: 'bed-e2e.mp4' })
    .filter({ hasText: 'Imagem + fala' })
    .first();
  await expect(savedIncident).toBeVisible({ timeout: 10_000 });
  await savedIncident.click();
  await page.locator('app-incident-panel details')
    .filter({ hasText: 'bed-e2e.mp4' })
    .getByRole('button', { name: 'Consultar alterações e evidências anteriores' })
    .click();
  await expect(page.getByRole('heading', { name: /Auditoria · incidente/ })).toBeVisible();
  await expect(page.locator('app-incident-panel')).toContainText('Estou com falta de ar.');
});

test('queries synthetic local FHIR vital signs and medication orders with explicit authorization', async ({ page }) => {
  await page.goto('/telemetry');
  const patient = page.getByLabel('Identificador FHIR do paciente');
  const authorization = page.getByLabel(/Confirmo autorização para consultar este prontuário/);
  const query = page.getByRole('button', { name: 'Consultar FHIR' });
  await expect(query).toBeDisabled();
  await patient.fill('synthetic-patient');
  await authorization.check();
  await query.click();
  const vital = page.locator('.import-result').filter({ hasText: 'FHIR R4 · sinais vitais' }).first();
  await expect(vital).toContainText('1 registro(s)', { timeout: 15_000 });
  await vital.locator('summary').click();
  await expect(vital).toContainText('FC 132 bpm');
  await expect(vital).toContainText('SpO₂ indisponível');
  await expect(patient).toHaveValue('');
  await expect(authorization).not.toBeChecked();

  await patient.fill('synthetic-patient');
  await page.getByLabel('Dados para importar').selectOption('prescriptions');
  await authorization.check();
  await query.click();
  const medication = page.locator('.import-result').filter({ hasText: 'FHIR R4 · prescrições' }).first();
  await expect(medication).toContainText('1 registro(s)', { timeout: 15_000 });
  await medication.locator('summary').click();
  await expect(medication).toContainText('dose(s) ausentes ou complexas não foram interpretadas');
  await expect(page.locator('.timeline-scroll')).toContainText('Medicamento sintético');
});

test('physiotherapy upload persists posture, analyzes frames and downloads a report in the real browser', async ({ page }) => {
  await page.goto('/video');
  await expect(page.getByRole('heading', { name: 'Análise de vídeos de fisioterapia' })).toBeVisible();
  await page.getByLabel('Postura do exercício').selectOption('standing');
  await uploadVideo(page, physioVideo);
  await expect(page.getByText('Arquivo: fisio-e2e.mp4')).toBeVisible();
  await page.getByRole('button', { name: 'Enviar e analisar' }).click();
  const recording = page.getByRole('button', { name: /fisio-e2e\.mp4/ });
  await expect(recording).toContainText('Pronto', { timeout: 30_000 });
  await recording.click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: '↓ Baixar relatório' }).click();
  const report = await download;
  expect(report.suggestedFilename()).toMatch(/^analise-.*\.json$/);
  const reportPath = path.join(temporaryDirectory, report.suggestedFilename());
  await report.saveAs(reportPath);
  const parsed = JSON.parse(readFileSync(reportPath, 'utf8'));
  expect(parsed.video.mode).toBe('fisio');
  expect(parsed.video.posture_config.type).toBe('standing');
  expect(Array.isArray(parsed.events)).toBe(true);
});

test('consultation import honors consent and presents offline Speech/Language review through the browser', async ({ page }) => {
  await page.goto('/voice');
  await expect(page.getByRole('heading', { name: 'Voz e transcrição' })).toBeVisible();
  const file = page.locator('input[type="file"][accept=".wav,.mp3,.m4a,.ogg,.flac,.webm,.aac"]');
  await expect(file).toBeDisabled();
  await page.getByLabel(/Confirmo autorização para processar/).check();
  await file.setInputFiles(consultation);
  await expect(page.getByRole('heading', { name: 'Voz e transcrição' })).toBeVisible();
  await expect(page.getByText('Estou com falta de ar.').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('alert').filter({ hasText: 'Prioridade de revisão: alta' }).first()).toBeVisible();
});

test('camera monitoring runs with Chromium fake devices and actual AudioWorklet, fuses evidence and preserves it when closed', async ({ page }) => {
  await page.goto('/telemetry');
  await page.getByRole('tab', { name: /Leito com câmera/ }).click();
  await page.getByRole('button', { name: 'Abrir câmera' }).click();
  await expect(page.getByText('PRÉVIA · NÃO ANALISANDO')).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'Salvar e aplicar cerca da câmera' }).click();
  await expect(page.getByText(/Posições da cerca salvas no servidor/)).toBeVisible();
  await page.getByRole('button', { name: 'Iniciar monitoramento com imagem e áudio' }).click();
  await expect(page.getByText('Monitoramento aplicado · captura de imagem e áudio ativa')).toBeVisible({
    timeout: 15_000,
  });
  const incident = page.locator('app-incident-panel article.multimodal');
  await expect(incident).toContainText('Saída da cerca virtual', { timeout: 30_000 });
  await expect(incident).toContainText('Estou com falta de ar.', { timeout: 30_000 });
  await expect(incident).toContainText(/imagem \+ fala/i);
  await page.getByRole('button', { name: 'Parar monitoramento e finalizar' }).click();
  await expect(page.getByText(/Sessão encerrada\. Cerca e histórico preservados/)).toBeVisible({
    timeout: 15_000,
  });
  await page.getByRole('button', { name: 'Consultar / atualizar histórico unificado' }).click();
  await expect(page.locator('app-incident-panel').getByText(/Câmera.*Imagem \+ fala/).first())
    .toBeVisible({ timeout: 10_000 });
});

test('imports synthetic vital series, prescription history and consented clinical text into the review timeline', async ({ page }) => {
  await page.goto('/telemetry');
  await expect(page.getByRole('heading', { name: 'Séries, prescrições e texto clínico' })).toBeVisible();
  await page.locator('#vitals-file').setInputFiles(path.resolve(
    process.cwd(), '..', 'backend', 'evaluation', 'examples', 'synthetic_vitals_24h.csv',
  ));
  await expect(page.locator('.import-result').filter({ hasText: 'synthetic_vitals_24h.csv' }))
    .toContainText('96 registro(s)', { timeout: 15_000 });
  await expect(page.locator('.import-result').filter({ hasText: 'synthetic_vitals_24h.csv' }))
    .toContainText('evento(s) para revisão');

  await page.locator('#prescriptions-file').setInputFiles(path.resolve(
    process.cwd(), '..', 'backend', 'evaluation', 'examples', 'synthetic_prescriptions.json',
  ));
  await expect(page.locator('.import-result').filter({ hasText: 'synthetic_prescriptions.json' }))
    .toContainText('5 registro(s)', { timeout: 15_000 });

  const noteFile = page.locator('#note-file');
  await expect(noteFile).toBeDisabled();
  await page.getByLabel(/Autorizo enviar o texto selecionado/).check();
  await noteFile.setInputFiles(path.resolve(
    process.cwd(), '..', 'backend', 'evaluation', 'examples', 'synthetic_clinical_note.json',
  ));
  await expect(page.locator('.import-result').filter({ hasText: 'synthetic_clinical_note.json' }))
    .toContainText('Azure AI Language', { timeout: 15_000 });
  await expect(page.getByRole('heading', {
    name: 'Eventos para revisão · dados importados e vídeo/áudio',
  })).toBeVisible();
  await expect(page.locator('.timeline-scroll')).toContainText('SpO₂');
});
