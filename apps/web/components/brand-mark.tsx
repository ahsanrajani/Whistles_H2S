export function BrandMark({size = 38}: {size?: number}) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <circle cx="12" cy="12" r="9.6" fill="none" stroke="var(--foreground)" strokeWidth="1.6"/>
      <path d="M12 6.5v11M8.4 9v6M15.6 9v6M5.2 10.6v2.8M18.8 10.6v2.8" stroke="#3DD283" strokeWidth="1.9" strokeLinecap="round" fill="none"/>
    </svg>
  );
}
