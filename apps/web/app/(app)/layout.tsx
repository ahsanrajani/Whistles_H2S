// The tenant/project layout (t/[tenant]/p/[project]/layout.tsx) owns the auth
// gate and the app shell. This group layout is a pass-through so the legacy
// redirect page and the tenant tree can coexist under one route group.
export default function AppGroupLayout({children}: {children: React.ReactNode}) {
  return <>{children}</>;
}
