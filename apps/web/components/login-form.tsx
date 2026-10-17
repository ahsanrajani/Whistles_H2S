"use client";
import {useRouter, useSearchParams} from "next/navigation";
import {useState, type FormEvent} from "react";
import {apiFetch, clearCsrf} from "@/lib/api";
import type {Auth} from "@/lib/types";
import {BrandMark} from "@/components/brand-mark";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Input} from "@/components/ui/input";

export default function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPending(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const auth = await apiFetch<Auth>("/auth/login", {method: "POST", body: JSON.stringify({username: data.get("username"), password: data.get("password")})});
      clearCsrf();
      // Hamza: "by default available when logging in" -- only for a role
      // that actually has a Care shift to be available for.
      if (auth.user.perms.includes("care:view")) {
        void apiFetch("/care/session", {method: "POST", body: JSON.stringify({state: "ready"})}).catch(() => {});
      }
      const next = params.get("next");
      router.replace(next?.startsWith("/") && !next.startsWith("//") ? next : "/");
      router.refresh();
    } catch (caught) {setError(caught instanceof Error ? caught.message : "Sign in failed"); setPending(false);}
  }
  return <main className="grid min-h-screen place-items-center bg-[radial-gradient(circle_at_top_left,rgba(109,94,246,.18),transparent_35%),radial-gradient(circle_at_bottom_right,rgba(34,211,238,.12),transparent_32%)] p-6">
    <Card className="w-full max-w-md p-5">
      <div className="mb-8 flex items-center gap-3"><BrandMark size={44}/><div><p className="m-0 text-3xl font-bold leading-tight">Whistles</p><p className="font-onest m-0 text-sm text-muted-foreground"></p><p className="m-0 mt-1 text-sm text-muted-foreground">Listening intelligence, with evidence</p></div></div>
      <h1 className="text-3xl font-semibold tracking-tight">Welcome back</h1><p className="mb-6 text-sm text-muted-foreground">Sign in to open your workspace.</p>
      <form onSubmit={submit} className="grid gap-4"><label className="grid gap-1.5 text-sm font-medium">Username<Input name="username" autoComplete="username" required autoFocus/></label><label className="grid gap-1.5 text-sm font-medium">Password<Input name="password" type="password" autoComplete="current-password" required/></label>{error && <p role="alert" className="m-0 rounded-[0.625rem] bg-danger/10 p-3 text-sm text-danger">{error}</p>}<Button type="submit" disabled={pending}>{pending ? "Signing in…" : "Sign in"}</Button></form>
    </Card>
  </main>;
}
