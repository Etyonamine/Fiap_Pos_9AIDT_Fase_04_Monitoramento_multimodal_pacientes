const { existsSync, readFileSync, rmSync } = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');

function request(pathname, method) {
  return new Promise((resolve, reject) => {
    const request = http.request(
      { host: '127.0.0.1', port: 8011, path: pathname, method },
      (response) => {
        response.resume();
        response.on('end', () => resolve(response.statusCode));
      },
    );
    request.setTimeout(2_000, () => request.destroy(new Error('E2E shutdown request timed out.')));
    request.on('error', reject);
    request.end();
  });
}

async function stopServer() {
  let shutdownInitiated = false;
  try {
    const status = await request('/e2e-shutdown', 'POST');
    if (status !== 200) throw new Error(`E2E backend shutdown returned HTTP ${status}.`);
  } catch (error) {
    if (error.code === 'ECONNREFUSED') return;
    if (error.code !== 'ECONNRESET') throw error;
    shutdownInitiated = true;
  }

  for (let attempt = 0; attempt < 50; attempt++) {
    try {
      await request('/e2e-health', 'GET');
    } catch (error) {
      if (error.code === 'ECONNREFUSED') return;
      if (error.code !== 'ECONNRESET') throw error;
      shutdownInitiated = true;
    }
    if (shutdownInitiated) await new Promise((resolve) => setTimeout(resolve, 100));
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error('E2E backend did not stop within 5 seconds.');
}

module.exports = async function globalTeardown() {
  const marker = path.join(__dirname, 'results', '.backend-data-path');
  if (!existsSync(marker)) return;

  const dataDirectory = path.resolve(readFileSync(marker, 'utf8'));
  if (
    path.dirname(dataDirectory) !== path.resolve(os.tmpdir()) ||
    !path.basename(dataDirectory).startsWith('ytos-e2e-backend-')
  ) {
    throw new Error('Refusing to remove an unrecognized E2E temporary directory.');
  }
  await stopServer();
  for (let attempt = 0; existsSync(marker) && attempt < 50; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  rmSync(dataDirectory, { recursive: true, force: true });
  rmSync(marker, { force: true });
};
