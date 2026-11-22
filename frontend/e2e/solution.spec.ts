import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test, expect, type Page } from '@playwright/test';

const temporaryDirectory = mkdtempSync(path.join(os.tmpdir(), 'ytos-e2e-'));
const bedVideo = path.join(temporaryDirectory, 'bed-e2e.mp4');
const physioVideo = path.join(temporaryDirectory, 'fisio-e2e.mp4');
const consultation = path.join(temporaryDirectory, 'consult-e2e.wav');
const referenceVoice = path.join(temporaryDirectory, 'referencia-e2e.wav');

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
  ffmpeg([
    '-f', 'lavfi', '-i', 'sine=frequency=180:sample_rate=16000', '-t', '2',
    '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', referenceVoice,
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

test('synthetic physiotherapy frames produce a measurable deviation in the downloaded report', async ({ page }) => {
  await page.goto('/video');
  await expect(page.getByRole('heading', { name: 'Análise de vídeos de fisioterapia' })).toBeVisible();
  await page.getByLabel('Postura do exercício').selectOption('standing');
  await uploadVideo(page, physioVideo);
  await expect(page.getByText('Arquivo: fisio-e2e.mp4')).toBeVisible();
  await page.getByRole('button', { name: 'Enviar e analisar' }).click();
  const recording = page.locator('button.file[aria-pressed="true"]').filter({ hasText: 'fisio-e2e.mp4' });
  await expect(recording).toContainText('Pronto', { timeout: 30_000 });
  await recording.click();
  await page.getByLabel('Limite do ângulo interno do joelho em graus').fill('150');
  const updatedThresholds = page.waitForResponse(response =>
    response.url().endsWith('/thresholds') && response.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: 'Salvar limites e recalcular' }).click();
  const thresholdResponse = await updatedThresholds;
  expect(thresholdResponse.ok()).toBeTruthy();
  expect((await thresholdResponse.json()).thresholds.knee_angle).toBe(150);
  await expect(page.getByRole('button', { name: 'Salvar limites e recalcular' })).toBeEnabled({
    timeout: 15_000,
  });
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: '↓ Baixar relatório' }).click();
  const report = await download;
  expect(report.suggestedFilename()).toMatch(/^analise-.*\.json$/);
  const reportPath = path.join(temporaryDirectory, report.suggestedFilename());
  await report.saveAs(reportPath);
  const parsed = JSON.parse(readFileSync(reportPath, 'utf8'));
  expect(parsed.video.mode).toBe('fisio');
  expect(parsed.video.posture_config.type).toBe('standing');
  expect(parsed.thresholds.knee_angle).toBe(150);
  expect(parsed.events).toContainEqual(expect.objectContaining({
    kind: 'Ângulo interno do joelho < 150°', severity: 'warning',
  }));
  expect(parsed.disclaimer).toContain('não');
});

test('synthetic audio acceptance measures a voice change alongside simulated Speech and Language', async ({ page }) => {
  await page.goto('/voice');
  await expect(page.getByRole('heading', { name: 'Voz e transcrição' })).toBeVisible();
  const file = page.locator('input[type="file"][accept=".wav,.mp3,.m4a,.ogg,.flac,.webm,.aac"]');
  await expect(file).toBeDisabled();
  await page.getByLabel(/Confirmo autorização para processar/).check();
  await file.setInputFiles(referenceVoice);
  await expect(page.locator('.overview')).toContainText('Análise concluída', { timeout: 30_000 });
  await expect(file).toBeEnabled();
  await file.setInputFiles(consultation);
  await expect(page.getByRole('heading', { name: 'Voz e transcrição' })).toBeVisible();
  await expect(page.getByText('Estou com falta de ar.').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.overview')).toContainText('SIMULAÇÃO: a transcrição');
  await expect(page.locator('.overview')).toContainText('tons, não fala');
  await expect(page.getByRole('alert').filter({ hasText: 'Prioridade de revisão: alta' }).first()).toBeVisible();
  await expect(page.locator('.overview')).toContainText('Análise concluída', { timeout: 30_000 });
  const language = page.locator('.supplementary details').nth(0);
  await language.locator('summary').click();
  await expect(language).toContainText('Origem da análise: Synthetic E2E');
  await expect(language).toContainText('falta de ar · menção não negada');

  const acoustics = page.locator('.supplementary details').nth(1);
  await acoustics.locator('summary').click();
  await acoustics.getByLabel('Gravação de referência', { exact: true })
    .selectOption({ label: 'referencia-e2e.wav' });
  await acoustics.getByRole('button', { name: 'Comparar características da fala' }).click();
  await expect(acoustics).toContainText('Diferenças acima dos limiares exploratórios');
  await expect(acoustics).toContainText('Pitch mediano');
  await expect(acoustics).toContainText('Diferença acústica e menção na transcrição para revisão');
  await expect(acoustics).toContainText('Menção na transcrição: falta de ar');
  await expect(acoustics).toContainText('A coexistência não demonstra causalidade');
});

test('camera monitoring runs with Chromium fake devices and actual AudioWorklet, fuses evidence and preserves it when closed', async ({ page }) => {
  await page.goto('/telemetry');
  await page.getByRole('tab', { name: /Leito com câmera/ }).click();
  await page.getByRole('button', { name: 'Abrir câmera' }).click();
  await expect(page.getByText('PRÉVIA · NÃO ANALISANDO')).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'Salvar e aplicar cerca da câmera' }).click();
  await expect(page.getByText(/Posições da cerca salvas no servidor/)).toBeVisible();
  const cameraStartResponse = page.waitForResponse(response =>
    response.url().endsWith('/api/camera/monitor') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Iniciar monitoramento com imagem e áudio' }).click();
  const cameraSession = await (await cameraStartResponse).json();
  await expect(page.getByText('Monitoramento aplicado · captura de imagem e áudio ativa')).toBeVisible({
    timeout: 15_000,
  });
  const incident = page.locator('app-incident-panel article.multimodal');
  await expect(incident).toContainText('Saída da cerca virtual', { timeout: 30_000 });
  await expect(incident).toContainText('Estou com falta de ar.', { timeout: 30_000 });
  await expect(incident).toContainText(/imagem \+ fala/i);
  const mediaResponse = await page.request.get(
    `http://127.0.0.1:8011/api/camera/monitor/${cameraSession.id}`,
  );
  expect(mediaResponse.ok()).toBeTruthy();
  const mediaSession = await mediaResponse.json();
  const evidence = mediaSession.events.find((event: { source: string }) =>
    event.source === 'image' || event.source === 'audio',
  );
  expect(evidence).toBeTruthy();
  const recordedAt = new Date(
    Date.parse(cameraSession.started_at) + evidence.timestamp * 1000,
  ).toISOString();
  const clinicalResponse = await page.request.post(
    `http://127.0.0.1:8011/api/clinical-stream/${cameraSession.id}/fhir-subscription?source_id=case-e2e`,
    {
      headers: { Authorization: 'Bearer synthetic-clinical-ingest-token-0123456789' },
      data: {
        resourceType: 'Bundle',
        type: 'collection',
        entry: [{
          resource: {
            resourceType: 'Observation',
            id: 'e2e-heart-rate',
            status: 'final',
            subject: { reference: 'Patient/case-e2e' },
            effectiveDateTime: recordedAt,
            code: { coding: [{ system: 'http://loinc.org', code: '8867-4' }] },
            valueQuantity: { value: 132, system: 'http://unitsofmeasure.org', code: '/min' },
          },
        }],
      },
    },
  );
  expect(clinicalResponse.status()).toBe(201);
  const clinicalStream = await clinicalResponse.json();
  const correlatedSample = clinicalStream.samples.find(
    (sample: { source_id: string }) => sample.source_id === 'case-e2e',
  );
  expect(correlatedSample.vitals.heart_rate_bpm).toBe(132);
  expect(correlatedSample.elapsed_seconds).toBeCloseTo(evidence.timestamp, 5);
  expect(correlatedSample.media_matches.length).toBeGreaterThan(0);
  await expect(page.locator('app-clinical-stream')).toContainText('FC 132 bpm', {
    timeout: 15_000,
  });
  await expect(page.locator('app-clinical-stream')).toContainText(
    'Correspondência temporal na mesma sessão',
  );
  await expect(page.locator('app-clinical-stream')).toContainText('Aceito pelo destino', {
    timeout: 15_000,
  });

  const medicationSampleId = '95e63454-782c-4c65-90ca-58a47185a001';
  const medicationResponse = await page.request.post(
    `http://127.0.0.1:8011/api/clinical-stream/${cameraSession.id}/samples`,
    {
      headers: { Authorization: 'Bearer synthetic-clinical-ingest-token-0123456789' },
      data: {
        sample_id: medicationSampleId,
        source_id: 'case-e2e',
        recorded_at: new Date(Date.parse(recordedAt) + 500).toISOString(),
        elapsed_seconds: evidence.timestamp + 0.5,
        prescriptions: [{
          medication: 'Medicamento sintético divergente',
          dose: 30,
          unit: 'mg',
          status: 'active',
          expected_regimen: { dose: 10, unit: 'mg', status: 'active' },
        }],
      },
    },
  );
  expect(medicationResponse.status()).toBe(201);
  const medicationResult = await medicationResponse.json();
  const medicationSample = medicationResult.samples.find(
    (sample: { sample_id: string }) => sample.sample_id === medicationSampleId,
  );
  expect(medicationSample.prescriptions[0].plan_comparison).toMatchObject({
    status: 'differs', different_fields: ['dose'],
  });
  expect(medicationSample.media_matches.length).toBeGreaterThan(0);
  expect(medicationSample.events).toContainEqual(expect.objectContaining({
    kind: 'unexpected_regimen', priority: 'review', delivery_id: expect.any(String),
  }));
  await expect.poll(async () => {
    const response = await page.request.get(
      `http://127.0.0.1:8011/api/clinical-stream/${cameraSession.id}`,
    );
    const stream = await response.json();
    const sample = stream.samples.find(
      (item: { sample_id: string }) => item.sample_id === medicationSampleId,
    );
    return sample?.events.find(
      (event: { kind: string }) => event.kind === 'unexpected_regimen',
    )?.delivery?.status;
  }, { timeout: 15_000 }).toBe('delivered');
  const medicationPanel = page.locator('app-clinical-stream .clinical-sample')
    .filter({ hasText: 'Medicamento sintético divergente' });
  await expect(medicationPanel).toContainText('30 mg', { timeout: 15_000 });
  await expect(medicationPanel).toContainText('referência 10 mg');
  await expect(medicationPanel).toContainText('divergência: dose');
  await expect(medicationPanel).toContainText('Aceito pelo destino');

  const simulator = page.locator('app-synthetic-stream');
  await simulator.getByRole('button', { name: 'Iniciar simulador de sinais e prescrição' }).click();
  await expect(simulator).toContainText('Frequência cardíaca acima do limite demonstrativo', { timeout: 20_000 });
  await expect(simulator).toContainText('SpO₂ abaixo do limite demonstrativo', { timeout: 10_000 });
  await expect(simulator).toContainText('FC 132 bpm', { timeout: 10_000 });
  await expect(simulator).toContainText('SpO₂ 88%', { timeout: 10_000 });
  await expect(simulator).toContainText('Referência sintética: 10 mg', { timeout: 10_000 });
  await expect(simulator).toContainText('divergência da referência fornecida nos campos dose', { timeout: 10_000 });
  await expect(simulator).toContainText('Nota sintética: Pessoa sintética relata bem-estar.', { timeout: 10_000 });
  await expect(simulator).toContainText('Nota sintética: Pessoa sintética relata cansaço.', { timeout: 10_000 });
  await expect(simulator).toContainText('Menção textual para revisão: cansaço', { timeout: 10_000 });
  await expect(simulator).toContainText('Recebido pelo webhook sintético local', { timeout: 10_000 });
  await expect(simulator).toContainText('incidente(s) de imagem/fala', { timeout: 10_000 });
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
    .toContainText('evento(s)');

  await page.locator('#prescriptions-file').setInputFiles(path.resolve(
    process.cwd(), '..', 'backend', 'evaluation', 'examples', 'synthetic_prescriptions.json',
  ));
  const prescriptions = page.locator('.import-result').filter({ hasText: 'synthetic_prescriptions.json' });
  await expect(prescriptions).toContainText('5 registro(s)', { timeout: 15_000 });
  await prescriptions.locator('summary').click();
  await expect(prescriptions).toContainText('Compatível nos campos informados');
  await expect(prescriptions).toContainText('Divergência nos campos: dose');
  await expect(prescriptions).toContainText('Sem referência explícita; esperado não avaliado');

  const noteFile = page.locator('#note-file');
  await expect(noteFile).toBeDisabled();
  await page.getByLabel(/Autorizo enviar o texto selecionado/).check();
  await noteFile.setInputFiles(path.resolve(
    process.cwd(), '..', 'backend', 'evaluation', 'examples', 'synthetic_clinical_note.json',
  ));
  const note = page.locator('.import-result').filter({ hasText: 'synthetic_clinical_note.json' });
  await expect(note).toContainText('Synthetic E2E', { timeout: 15_000 });
  await note.locator('summary').click();
  await expect(note).toContainText('Regra local e frase-chave: cansaço · menção não negada · cansaço');
  await expect(page.getByRole('heading', {
    name: 'Eventos para revisão · dados importados e vídeo/áudio',
  })).toBeVisible();
  await expect(page.locator('.timeline-scroll')).toContainText('SpO₂');
  await expect(page.locator('.timeline-scroll')).toContainText('Menção textual para revisão: cansaço');
});
