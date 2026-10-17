/** A small local score gauge -- plain SVG, same complexity class as the Venn
 * diagram it replaces in this folder. Not promoted to components/ui/ since
 * nothing outside the SEO tab needs a ring gauge yet. */
export function ScoreRing({score, size = 104, label}: {score: number; size?: number; label?: string}) {
  const stroke = 9;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const color = score >= 90 ? "var(--success)" : score >= 50 ? "var(--warning)" : "var(--danger)";
  return (
    <div className="flex flex-col items-center gap-1.5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label ?? `Score ${Math.round(score)} of 100`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth={stroke}/>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
                strokeDasharray={`${c * pct} ${c}`} strokeLinecap="round"
                transform={`rotate(-90 ${size / 2} ${size / 2})`}/>
        <text x="50%" y="52%" dominantBaseline="middle" textAnchor="middle" className="fill-foreground text-2xl font-bold">
          {Math.round(score)}
        </text>
      </svg>
      {label && <p className="m-0 text-xs text-muted-foreground">{label}</p>}
    </div>
  );
}
