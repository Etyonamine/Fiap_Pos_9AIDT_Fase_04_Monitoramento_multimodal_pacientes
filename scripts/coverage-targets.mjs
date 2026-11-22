export const QUALITY_TARGETS = Object.freeze({
  'backend/total': Object.freeze({ lines: 90, branches: 80 }),
  'backend/app-total': Object.freeze({ lines: 90, branches: 80 }),
  'frontend/total': Object.freeze({ lines: 90, branches: 80 }),
});

export function checkQualityTargets(measured) {
  const failures = [];
  for (const [scope, targets] of Object.entries(QUALITY_TARGETS)) {
    if (!measured[scope]) {
      failures.push(`${scope}: absent from coverage report (quality target)`);
      continue;
    }
    for (const [metric, target] of Object.entries(targets)) {
      const value = measured[scope][metric];
      if (!Number.isFinite(value) || value + 1e-9 < target) {
        const reported = Number.isFinite(value) ? value.toFixed(2) : String(value);
        failures.push(`${scope}: ${metric} ${reported}% < target ${target}%`);
      }
    }
  }
  return failures;
}
