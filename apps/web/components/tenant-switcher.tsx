"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {usePathname, useRouter} from "next/navigation";
import {useProjects, useWorkspaces} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {useTenant} from "@/lib/tenant";
import {Select} from "@/components/ui/select";

/**
 * Header tenant + project switcher (F0.2). Replaces the admin-only workspace
 * <Select>. A switch changes the URL — not just the server session — and keeps
 * the current surface. Only renders a control when there is a real choice, and
 * only lists what the user's roles permit (the API decides `can_switch`).
 */
export function TenantSwitcher() {
  const {tenant, project, base} = useTenant();
  const pathname = usePathname();
  const router = useRouter();
  const query = useQueryClient();
  const workspaces = useWorkspaces();
  const projects = useProjects();

  const surface = pathname.startsWith(base) ? pathname.slice(base.length) || "/overview" : "/overview";
  const canSwitchWs = !!workspaces.data?.can_switch && (workspaces.data.list.length ?? 0) > 1;
  const projList = projects.data?.projects ?? [];

  const switchWs = useMutation({
    mutationFn: (ws_id: number) =>
      apiFetch("/workspace/switch", {method: "POST", body: JSON.stringify({ws_id})}),
    onSuccess: async (_result, ws_id) => {
      const slug = workspaces.data?.list.find((w) => w.id === ws_id)?.slug;
      await query.invalidateQueries();
      router.push(slug ? `/t/${slug}/p/listening${surface}` : `${base}${surface}`);
    },
  });

  if (!canSwitchWs && projList.length <= 1) return null;

  return (
    <div className="hidden items-center gap-2 md:flex">
      {canSwitchWs && (
        <Select
          aria-label="Switch workspace"
          className="max-w-44"
          value={String(workspaces.data!.active?.id ?? "")}
          onChange={(event) => switchWs.mutate(Number(event.target.value))}>
          {workspaces.data!.list.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
          ))}
        </Select>
      )}
      {projList.length > 1 && (
        <Select
          aria-label="Switch project"
          className="max-w-40"
          value={project}
          onChange={(event) => router.push(`/t/${tenant}/p/${event.target.value}${surface}`)}>
          {projList.map((item) => (
            <option key={item.slug} value={item.slug}>{item.name}</option>
          ))}
        </Select>
      )}
    </div>
  );
}
