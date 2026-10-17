/**
 * The one place UI permission gates live (F0.3). Every nav item, gated button
 * and menu entry maps to a required `area:verb` grant here — never scattered
 * `role === "admin"` checks in components. The API still enforces; the UI only
 * hides what a role cannot do so nothing 403s on click.
 */

export type Perm = string; // "area:verb", e.g. "care:view"

export function can(perms: string[] | undefined, ...required: Perm[]): boolean {
  if (!perms) return false;
  return required.every((perm) => perms.includes(perm));
}

export function canAny(perms: string[] | undefined, ...required: Perm[]): boolean {
  if (!perms) return false;
  return required.some((perm) => perms.includes(perm));
}

/** Nav surface slug (without the /t/{tenant}/p/{project} prefix) -> the grant
 * needed to see it. A slug absent here is visible to any authenticated user. */
export const NAV_PERMS: Record<string, Perm> = {
  "/overview": "listening:view",
  "/care": "care:view",
  "/care/supervisor": "care:approve",
  "/knowledge": "templates:view",
  "/content": "templates:view",
  "/reports": "reporting:view",
  "/vantage": "reporting:view",
  "/seo": "reporting:view",
  "/mentions": "listening:view",
  "/sentiment": "listening:view",
  "/competitors": "listening:view",
  "/reviews": "listening:view",
  "/themes": "listening:view",
  "/scam": "listening:view",
  "/triage": "listening:view",
  "/switch-intent": "listening:view",
  "/incidents": "listening:view",
  "/product-lines": "listening:view",
  "/regulatory": "listening:view",
  "/branches": "listening:view",
  "/alerts": "listening:view",
  "/posts": "listening:view",
  "/impersonation": "admin:view",
  "/admin": "admin:view",
  "/admin-ops": "admin:view",
  "/review": "admin:view",
  "/onboarding": "admin:create",
};

/** Nav surface slug -> the feature-flag key that must be on for it to show.
 * Surface slugs map to `surface.<slug>`; a whole area maps to its `module.*`. */
export const NAV_FEATURES: Record<string, string> = {
  "/overview": "surface.overview",
  "/mentions": "surface.mentions",
  "/sentiment": "surface.sentiment",
  "/competitors": "surface.competitors",
  "/reviews": "surface.reviews",
  "/themes": "surface.themes",
  "/scam": "surface.scam",
  "/triage": "surface.triage",
  "/switch-intent": "surface.switch-intent",
  "/incidents": "surface.incidents",
  "/product-lines": "surface.product-lines",
  "/regulatory": "surface.regulatory",
  "/branches": "surface.branches",
  "/alerts": "surface.alerts",
  "/posts": "surface.posts",
  "/impersonation": "surface.impersonation",
  "/care": "module.care",
  "/care/supervisor": "module.care",
  "/knowledge": "module.care",
  "/reports": "module.reporting",
  "/content": "module.content",
  "/vantage": "module.vantage",
  "/seo": "module.seo",
};

/** A feature is off when its own key is false, or (for a listening surface)
 * when the whole `module.listening` is off. Missing map / missing flags -> on. */
export function featureEnabled(
  features: Record<string, boolean> | undefined, slug: string,
): boolean {
  if (!features) return true;
  const key = NAV_FEATURES[slug];
  if (!key) return true;
  if (features[key] === false) return false;
  if (key.startsWith("surface.") && features["module.listening"] === false) return false;
  return true;
}

/** Roles that carry Care oversight above a plain front-line Agent -- mirrors
 * apps/api/api_fastapi/deps.py::_CARE_OVERSIGHT_ROLES. A user with none of
 * these only sees/acts on their own assigned cases (Hamza, 2026-09-11:
 * "agent accounts should be able to access only the conversations assigned
 * to them, nothing else") -- the API enforces this either way; this is UX
 * only, so the console doesn't show tabs and buttons that would 403. */
const CARE_OVERSIGHT_ROLES = new Set(["senior_agent", "supervisor", "team_lead", "admin"]);

export function isAgentScoped(roles: string[] | undefined): boolean {
  if (!roles || roles.length === 0) return true;
  return !roles.some((r) => CARE_OVERSIGHT_ROLES.has(r));
}

// Hamza, 2026-09-11: "Supervisor/admin dashboard onboards to /overview,
// which they do not have access to, so shows an error. make sure that the
// first page loaded is the care console." Onboarding a role narrowed by
// 0033_care_console_scoping (agent/supervisor lost listening:view) straight
// to a hardcoded /overview landed them on a page they're immediately denied
// -- the post-login landing route has to be permission-aware like the nav
// already is, not a single hardcoded default for every role.
const LANDING_PRIORITY: [string, Perm][] = [
  ["/overview", "listening:view"],
  ["/care", "care:view"],
  ["/admin", "admin:view"],
  ["/reports", "reporting:view"],
  ["/knowledge", "templates:view"],
];

/** The first surface this permission set can actually open. `/care` is the
 * final fallback -- always a reasonable landing spot, never a dead end. */
export function defaultLandingSurface(perms: string[] | undefined): string {
  for (const [slug, required] of LANDING_PRIORITY) {
    if (can(perms, required)) return slug;
  }
  return "/care";
}

export function navVisible(
  perms: string[] | undefined, slug: string,
  features?: Record<string, boolean>,
): boolean {
  const required = NAV_PERMS[slug];
  if (required && !can(perms, required)) return false;
  return featureEnabled(features, slug);
}
