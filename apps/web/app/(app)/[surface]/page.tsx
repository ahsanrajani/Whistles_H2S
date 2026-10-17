import {notFound, redirect} from "next/navigation";
import {defaultTenantBase} from "@/lib/tenant-server";

// Legacy path parity (F0.1): the 18 surfaces used to live at /overview,
// /mentions, … They now live under /t/{tenant}/p/{project}/…; this catch-all
// redirects an old bookmark to the same surface under the user's active
// workspace, preserving the query string.
const SURFACES = new Set([
  "overview", "mentions", "sentiment", "competitors", "reviews", "themes",
  "scam", "triage", "switch-intent", "incidents", "product-lines",
  "regulatory", "branches", "alerts", "impersonation", "admin", "review",
  "onboarding", "vantage", "posts",
]);

export default async function LegacySurfaceRedirect({
  params,
  searchParams,
}: {
  params: Promise<{surface: string}>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const {surface} = await params;
  if (!SURFACES.has(surface)) notFound();

  const base = await defaultTenantBase();
  if (!base) redirect("/login");

  const sp = await searchParams;
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(sp)) {
    if (Array.isArray(value)) value.forEach((v) => qs.append(key, v));
    else if (value != null) qs.set(key, value);
  }
  const query = qs.toString();
  redirect(`${base}/${surface}${query ? `?${query}` : ""}`);
}
