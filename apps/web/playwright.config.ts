import { defineConfig } from '@playwright/test';
const externalServer = process.env.PLAYWRIGHT_EXTERNAL_SERVER === 'true';
export default defineConfig({
  testDir: './tests/e2e',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:3000',
    launchOptions: { args: ['--no-proxy-server'] },
  },
  webServer: externalServer ? undefined : {
    command: 'npm run start -- --hostname 127.0.0.1',
    url: 'http://127.0.0.1:3000',
    reuseExistingServer: false,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
