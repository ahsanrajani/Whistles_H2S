"use client";

import {Link} from "@/components/tenant-link";
import {useThemes} from "@/hooks/use-api";
import {Badge} from "./ui/badge";
import {Card} from "./ui/card";
import {PageHeader, ThemeCloud} from "./viewer-components";
import {EmptyState, ErrorState, LoadingState} from "./states";

export function ThemesView() {
  const result = useThemes();
  if (result.isLoading) return <LoadingState label="Loading themes…"/>;
  if (result.error) return <ErrorState message={result.error.message}/>;
  const data = result.data;
  if (!data?.table.length) return <div className="grid gap-6"><PageHeader title="Themes" subtitle={`Recurring conversation about ${data?.focus?.name ?? "the focus brand"}.`}/><EmptyState title="Not enough text to summarise themes" body="Collect more client-safe mention text; recurring terms will appear once they clear the minimum count."/></div>;
  return <div className="mx-auto grid max-w-[93.75rem] gap-5"><PageHeader title="Themes" subtitle={`Words and phrases recurring about ${data.focus?.name ?? "the focus brand"}, tinted by sentiment.`}/><Card><ThemeCloud themes={data.cloud}/></Card><Card><h2 className="mt-0 text-xl font-semibold">All themes</h2><div className="overflow-x-auto"><table className="w-full min-w-[38.75rem] border-collapse text-left text-sm"><thead><tr className="border-b text-xs text-muted-foreground"><th className="py-3">Term</th><th className="py-3 text-right">Mentions</th><th className="px-8 py-3">Lean</th><th className="py-3 text-right">Positive</th><th className="py-3 text-right">Negative</th></tr></thead><tbody>{data.table.map(theme => <tr key={theme.term} className="border-b last:border-0"><th className="py-4"><Link href={`/mentions?q=${encodeURIComponent(theme.term)}`} className="hover:text-primary">{theme.term}</Link></th><td className="numeric py-4 text-right">{theme.n}</td><td className="px-8 py-4"><Badge className={theme.lean === "negative" ? "border-danger/30 text-danger" : theme.lean === "positive" ? "border-success/30 text-success" : theme.lean === "mixed" ? "border-warning/30 text-warning" : "text-muted-foreground"}>{theme.lean === "unscored" ? "not scored" : theme.lean}</Badge></td><td className="numeric py-4 text-right text-muted-foreground">{theme.pos}</td><td className="numeric py-4 text-right text-muted-foreground">{theme.neg}</td></tr>)}</tbody></table></div></Card></div>;
}
