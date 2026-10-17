import {defineConfig} from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e", testMatch: "care-ux.spec.ts", workers: 1, retries: 0,
  timeout: 60_000, expect: {timeout: 15_000},
  use: {baseURL: "http://127.0.0.1:3100", browserName: "chromium"},
  webServer: [
    {command: "node tests/fixtures/care-api.mjs", url: "http://127.0.0.1:5100/api/v1/auth/me", reuseExistingServer: process.env.CARE_UX_REUSE === "1"},
    {command: "node ../../node_modules/next/dist/bin/next dev --port 3100",
      env: {GURU_API_ORIGIN: "http://127.0.0.1:5100"},
      url: "http://127.0.0.1:3100/login", reuseExistingServer: process.env.CARE_UX_REUSE === "1", timeout: 120_000},
  ],
});
