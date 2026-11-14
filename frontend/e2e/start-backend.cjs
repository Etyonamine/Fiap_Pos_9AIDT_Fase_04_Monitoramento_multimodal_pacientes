const { spawn } = require('node:child_process');
const { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const root = path.resolve(__dirname, '..', '..');
const venv = process.platform === 'win32'
  ? path.join(root, 'backend', '.venv', 'Scripts', 'python.exe')
  : path.join(root, 'backend', '.venv', 'bin', 'python');
const python = process.env.E2E_PYTHON || (existsSync(venv) ? venv : 'python');
const dataDirectory = mkdtempSync(path.join(os.tmpdir(), 'ytos-e2e-backend-'));
const marker = path.join(__dirname, 'results', '.backend-data-path');
mkdirSync(path.dirname(marker), { recursive: true });
writeFileSync(marker, dataDirectory, 'utf8');
const child = spawn(python, [path.join(root, 'backend', 'tests', 'e2e_server.py')], {
  cwd: root,
  stdio: 'inherit',
  env: { ...process.env, VIDEO_DATA_DIR: dataDirectory },
});
child.on('error', (error) => { console.error(error); process.exitCode = 1; });
child.on('close', (code) => {
  rmSync(marker, { force: true });
  process.exitCode = code ?? 1;
});
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => child.kill(signal));
}
