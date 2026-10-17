import {redirect} from "next/navigation";
import {getMe} from "@/lib/auth";
import {defaultLandingSurface} from "@/lib/permissions";

// Hamza: "make sure that the first page loaded is the care console" (for a
// role, e.g. supervisor, scoped off listening:view -- a hardcoded /overview
// here was a landing dead-end since 0033_care_console_scoping). The layout
// above this route already enforces auth; this only needs perms to pick
// the right surface.
export default async function ProjectHome({
  params,
}: {
  params: Promise<{tenant: string; project: string}>;
}) {
  const {tenant, project} = await params;
  const auth = await getMe();
  redirect(`/t/${tenant}/p/${project}${defaultLandingSurface(auth?.user.perms)}`);
}
