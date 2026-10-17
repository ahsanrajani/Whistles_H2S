"use client";

import NextLink from "next/link";
import {useRouter as useNextRouter} from "next/navigation";
import {forwardRef, type ComponentProps} from "react";
import {tenantPath, useOptionalTenant} from "@/lib/tenant";

type LinkProps = ComponentProps<typeof NextLink>;

/**
 * Drop-in replacement for `next/link` that prefixes absolute in-app paths with
 * the current `/t/{tenant}/p/{project}` base. External URLs, `/api`, `/login`,
 * `/brand`, hash links and already-prefixed paths pass through untouched.
 */
export const Link = forwardRef<HTMLAnchorElement, LinkProps>(function Link({href, ...rest}, ref) {
  const {base} = useOptionalTenant();
  const next = typeof href === "string" ? tenantPath(base, href) : href;
  return <NextLink ref={ref} href={next} {...rest}/>;
});

/** `(href) => prefixed href` — for the handful of plain `<a>` tags whose href
 * is conditionally an external URL. */
export function useTenantHref(): (href: string) => string {
  const {base} = useOptionalTenant();
  return (href) => tenantPath(base, href);
}

type Nav = ReturnType<typeof useNextRouter>;

/** `useRouter` whose `push`/`replace` prefix a string path with the tenant base. */
export function useTenantRouter(): Nav {
  const router = useNextRouter();
  const {base} = useOptionalTenant();
  return {
    ...router,
    push: (href, opts) => router.push(typeof href === "string" ? tenantPath(base, href) : href, opts),
    replace: (href, opts) => router.replace(typeof href === "string" ? tenantPath(base, href) : href, opts),
  };
}
