import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests', fullyParallel: false, timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:5173', browserName: 'chromium', channel: process.env.PLAYWRIGHT_CHANNEL as 'chrome' | undefined, trace: 'retain-on-failure' },
  reporter: 'list',
})
