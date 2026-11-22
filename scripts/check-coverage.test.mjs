import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, rmdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { checkQualityTargets, QUALITY_TARGETS } from './coverage-targets.mjs';
import test from 'node:test';

const checker = new URL('./check-coverage.mjs', import.meta.url);
const baseline = JSON.parse(readFileSync(new URL('./coverage-baseline.json', import.meta.url), 'utf8'));

function withBaseline(contents, action) {
  const directory = mkdtempSync(path.join(tmpdir(), 'quality-gate-'));
  const file = path.join(directory, 'baseline.json');
  try {
    writeFileSync(file, JSON.stringify(contents));
    action(file);
  } finally {
    rmSync(file);
    rmdirSync(directory);
  }
}

const run = (file, ...args) => spawnSync(process.execPath, [
  fileURLToPath(checker), '--baseline', file, ...args,
], { encoding: 'utf8' });

test('coverage gate accepts current measured baseline', () => {
  withBaseline(baseline, file => assert.equal(run(file).status, 0));
});

test('coverage gate rejects regression and absent modules', () => {
  withBaseline({
    ...baseline, 'frontend/total': { lines: 100, branches: 100 },
    'backend/app/missing.py': { lines: 100, branches: 100 },
  }, file => {
    const result = run(file);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /frontend\/total: lines/);
    assert.match(result.stderr, /missing.py: absent/);
  });
});

test('baseline updates cannot lower previous thresholds or forget missing modules', () => {
  withBaseline({
    ...baseline, 'frontend/total': { lines: 100, branches: 100 },
    'backend/app/missing.py': { lines: 99, branches: 99 },
  }, file => {
    assert.equal(run(file, '--write-baseline').status, 0);
    const updated = JSON.parse(readFileSync(file, 'utf8'));
    assert.deepEqual(updated['frontend/total'], { lines: 100, branches: 100 });
    assert.deepEqual(updated['backend/app/missing.py'], { lines: 99, branches: 99 });
  });
});

test('quality targets accept the minimum 90% lines and 80% branches', () => {
  const measured = Object.fromEntries(Object.keys(QUALITY_TARGETS).map(scope => [
    scope, { lines: 90, branches: 80 },
  ]));
  assert.deepEqual(checkQualityTargets(measured), []);
});

test('quality targets reject coverage below either minimum', () => {
  const measured = Object.fromEntries(Object.keys(QUALITY_TARGETS).map(scope => [
    scope, { lines: 89.99, branches: 79.99 },
  ]));
  assert.deepEqual(checkQualityTargets(measured), [
    'backend/total: lines 89.99% < target 90%',
    'backend/total: branches 79.99% < target 80%',
    'backend/app-total: lines 89.99% < target 90%',
    'backend/app-total: branches 79.99% < target 80%',
    'frontend/total: lines 89.99% < target 90%',
    'frontend/total: branches 79.99% < target 80%',
  ]);
});
