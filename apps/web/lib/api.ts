const API_ROOT = "/api/v1";
let csrfToken: string | null = null;

export class ApiError extends Error {
  constructor(public status: number, message: string) {super(message);}
}

export async function getCsrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  const response = await fetch(`${API_ROOT}/csrf`, {credentials: "include", cache: "no-store"});
  if (!response.ok) throw new ApiError(response.status, "Could not initialise security token");
  csrfToken = (await response.json() as {token: string}).token;
  return csrfToken;
}

export function clearCsrf() {csrfToken = null;}

// Hamza, 2026-09-11: "logout if session disconnects" -- a 401 from a real
// protected route (not the auth-flow endpoints themselves, which legitimately
// 401 while logged out) means the server-side session is gone -- idle
// timeout, deleted, a restarted session store. Bounce to a real login page
// rather than leave every open tab showing a broken, half-authenticated UI.
// A hard navigation (not router.replace) is deliberate: it drops all
// in-memory state, including whatever this session's own client-side idle
// timer (use-idle-logout.ts) or a stale React Query cache still holds.
const AUTH_FLOW_PATHS = new Set(["/csrf", "/auth/me", "/auth/login", "/auth/logout"]);

function handleSessionExpired(path: string) {
  if (AUTH_FLOW_PATHS.has(path) || typeof window === "undefined") return;
  clearCsrf();
  if (!window.location.pathname.startsWith("/login")) {
    // Deliberately a hard navigation, not useRouter().push()/redirect() --
    // this runs from a plain lib function with no router access, and a
    // forced-logout genuinely wants a full reload: it drops every in-memory
    // React Query cache and idle timer client-side navigation would leave behind.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/login";
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("X-CSRF-Token", await getCsrf());
    // A FormData body (file upload) must NOT get an explicit Content-Type --
    // the browser sets multipart/form-data with its own boundary itself.
    if (init.body && !headers.has("Content-Type") && !(init.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
  }
  const response = await fetch(`${API_ROOT}${path}`, {...init, headers, credentials: "include", cache: "no-store"});
  if (!response.ok) {
    if (response.status === 401) handleSessionExpired(path);
    const body = await response.json().catch(() => ({error: response.statusText})) as {error?: string};
    throw new ApiError(response.status, body.error ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}
