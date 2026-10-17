import {redirect} from "next/navigation";
import {getMe} from "@/lib/auth";
import {AppShell} from "@/components/app-shell";
import {TenantProvider} from "@/lib/tenant";

export default async function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{tenant: string; project: string}>;
}) {
  const {tenant, project} = await params;
  const auth = await getMe();
  if (!auth) redirect("/login");
  return (
    <TenantProvider tenant={tenant} project={project}>
      <AppShell initialUser={auth.user} tenant={tenant} project={project}>
        {children}
      </AppShell>
    </TenantProvider>
  );
}
