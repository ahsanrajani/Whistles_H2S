"use client";

import {createContext, useContext, useMemo, type ReactNode} from "react";

type TenantValue = {tenant: string; project: string; base: string};

const TenantContext = createContext<TenantValue | null>(null);

/** Paths that must never be rewritten under the tenant prefix. */
const PASSTHROUGH = /^(https?:|mailto:|tel:|#|\/api\/|\/login|\/brand\/|\/t\/)/;

export function tenantPath(base: string, href: string): string {
  if (!href.startsWith("/")) return href;         // relative / hash-only
  if (PASSTHROUGH.test(href)) return href;         // api, login, brand, already-prefixed
  return `${base}${href}`;
}

export function TenantProvider({tenant, project, children}: {tenant: string; project: string; children: ReactNode}) {
  const value = useMemo<TenantValue>(
    () => ({tenant, project, base: `/t/${tenant}/p/${project}`}),
    [tenant, project],
  );
  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant(): TenantValue {
  const value = useContext(TenantContext);
  if (!value) throw new Error("useTenant must be used within a TenantProvider");
  return value;
}

/** Optional variant for code that may render outside a provider (defaults to no prefix). */
export function useOptionalTenant(): TenantValue {
  return useContext(TenantContext) ?? {tenant: "", project: "", base: ""};
}
