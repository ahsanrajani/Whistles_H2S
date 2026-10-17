import {defineConfig, devices} from "@playwright/test";

/**
 * End-to-end journey for the migration UI. Boots the two-process dev stack
 * (Flask :5000 + Next :3000) via the repo-root `npm run dev` unless one is
 * already up. Requires a one-time `npx playwright install chromium`.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  // The suite runs against the Turbopack DEV server, which compiles each route
  // on first visit — cold compiles of the chart-heavy surfaces (branches,
  // sentiment) routinely take >10s on a loaded host. Generous timeouts + one
  // retry absorb that; a production build is covered by `npm run check:web`.
  timeout: 90_000,
  expect: {timeout: 30_000},
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  projects: [{name: "chromium", use: {...devices["Desktop Chrome"]}}],
  webServer: {
    command: "npm run dev",
    cwd: "../..",
    // Wait on the API (:5000), not just Next (:3000) — the API runs migrations +
    // seed on boot and is the slower of the two. Every page's server render
    // calls /auth/me, so testing before the API answers just bounces to /login.
    url: "http://127.0.0.1:5000/api/v1/csrf",
    reuseExistingServer: true,
    timeout: 180_000,
    stdout: "pipe",
  },
});
