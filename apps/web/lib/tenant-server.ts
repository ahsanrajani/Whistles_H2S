import {getMe} from "./auth";
import {defaultLandingSurface} from "./permissions";

/**
 * The `/t/{tenant}/p/{project}` base for the signed-in user's active workspace,
 * defaulting the project to `listening`. Returns null when not authenticated.
 * Server-only (uses `getMe`, which reads cookies).
 */
export async function defaultTenantBase(project = "listening"): Promise<string | null> {
  const auth = await getMe();
  const slug = auth?.user.workspace?.slug;
  if (!slug) return null;
  return `/t/${slug}/p/${project}`;
}

/** `defaultTenantBase()` plus the first surface this user's permissions can
 * actually open (e.g. `/care` for a role scoped off listening:view) --
 * `${base}/overview` is a landing dead-end for supervisor/agent roles since
 * 0033_care_console_scoping. Returns null when not authenticated. */
export async function defaultLandingPath(project = "listening"): Promise<string | null> {
  const auth = await getMe();
  const slug = auth?.user.workspace?.slug;
  if (!slug) return null;
  return `/t/${slug}/p/${project}${defaultLandingSurface(auth!.user.perms)}`;
}
