import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { checkQualityTargets } from './coverage-targets.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const baselineArgument = process.argv.indexOf('--baseline');
if (baselineArgument >= 0 && !process.argv[baselineArgument + 1]) {
  throw new Error('--baseline requires a JSON path');
}
const baselinePath = baselineArgument < 0 ? path.join(root, 'scripts', 'coverage-baseline.json')
  : path.resolve(process.argv[baselineArgument + 1]);
const read = file => JSON.parse(readFileSync(file, 'utf8'));
const normalize = file => file.replaceAll('\\', '/');
const percentage = (covered, total) => total === 0 ? 100 : covered * 100 / total;
const backend = read(path.join(root, 'backend', 'coverage.json'));
const frontend = read(path.join(root, 'frontend', 'coverage', 'frontend', 'coverage-summary.json'));
const measured = {};
for (const [file, details] of Object.entries(backend.files)) {
  const summary = details.summary;
  measured[`backend/${normalize(file)}`] = {
    lines: percentage(summary.covered_lines, summary.num_statements),
    branches: percentage(summary.covered_branches, summary.num_branches),
  };
}
measured['backend/total'] = {
  lines: percentage(backend.totals.covered_lines, backend.totals.num_statements),
  branches: percentage(backend.totals.covered_branches, backend.totals.num_branches),
};
const appSummaries = Object.entries(backend.files)
  .filter(([file]) => normalize(file).startsWith('app/'))
  .map(([, details]) => details.summary);
measured['backend/app-total'] = {
  lines: percentage(
    appSummaries.reduce((sum, item) => sum + item.covered_lines, 0),
    appSummaries.reduce((sum, item) => sum + item.num_statements, 0),
  ),
  branches: percentage(
    appSummaries.reduce((sum, item) => sum + item.covered_branches, 0),
    appSummaries.reduce((sum, item) => sum + item.num_branches, 0),
  ),
};
for (const [file, details] of Object.entries(frontend)) {
  const relative = file === 'total' ? 'total' : normalize(path.relative(root, file));
  measured[file === 'total' ? 'frontend/total' : relative] = {
    lines: percentage(details.lines.covered, details.lines.total),
    branches: percentage(details.branches.covered, details.branches.total),
  };
}

if (process.argv.includes('--write-baseline')) {
  const previous = existsSync(baselinePath) ? read(baselinePath) : {};
  const floors = Object.fromEntries(Object.entries(measured).map(([file, metrics]) => [
    file, Object.fromEntries(Object.entries(metrics).map(([metric, value]) => [
      metric, Math.max(previous[file]?.[metric] ?? 0, Math.floor(value * 100) / 100),
    ])),
  ]));
  for (const [file, metrics] of Object.entries(previous)) {
    if (!(file in floors)) floors[file] = metrics;
  }
  writeFileSync(baselinePath, `${JSON.stringify(floors, null, 2)}\n`);
  console.log('Baseline written. Review changes; never lower thresholds to make CI pass.');
} else {
  const baseline = read(baselinePath);
  const failures = [];
  for (const [file, thresholds] of Object.entries(baseline)) {
    if (!measured[file]) {
      failures.push(`${file}: absent from coverage report`);
      continue;
    }
    for (const [metric, floor] of Object.entries(thresholds)) {
      const value = measured[file][metric];
      if (!Number.isFinite(value) || value + 1e-9 < floor) {
        failures.push(`${file}: ${metric} ${value.toFixed(2)}% < ${floor}%`);
      }
    }
  }
  for (const file of Object.keys(measured)) {
    if (!(file in baseline)) failures.push(`${file}: missing reviewed baseline`);
  }
  failures.push(...checkQualityTargets(measured));
  if (failures.length) {
    console.error(failures.join('\n'));
    process.exitCode = 1;
  } else {
    console.log(`Coverage floors passed for ${Object.keys(baseline).length} modules/totals.`);
    console.log(JSON.stringify({
      backend: measured['backend/total'], frontend: measured['frontend/total'],
      backendApp: measured['backend/app-total'],
    }, null, 2));
  }
}
