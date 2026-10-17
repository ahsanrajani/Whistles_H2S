"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";
import {useCareCase} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import type {EditableCustomerField} from "@/lib/types";
import {ChannelBadge} from "./primitives";
import {Card} from "@/components/ui/card";

function fmtDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString();
}

// Hamza (Customer panel screenshot): "these details should be editable."
// (label, field key, kind) for the fields that are genuinely a stored,
// manually-correctable fact -- not the platform/handle match key, and not
// one of the case-derived stats below (lifetime/open cases, first contact,
// last activity, ...), which stay computed and read-only.
const EDITABLE_FIELDS: [string, EditableCustomerField, "text" | "bool"][] = [
  ["Full name", "display_name", "text"],
  ["Preferred name", "preferred_name", "text"],
  ["Other handles", "other_handles", "text"],
  ["Email", "email", "text"],
  ["Phone / mobile", "phone", "text"],
  ["Location", "location", "text"],
  ["Country", "country", "text"],
  ["Language", "language", "text"],
  ["Timezone", "timezone", "text"],
  ["Customer segment", "segment", "text"],
  ["Account status", "account_status", "text"],
  ["VIP", "vip", "bool"],
  ["Blocked", "blocked", "bool"],
  ["Preferred channel", "preferred_channel", "text"],
  ["Tags", "tags", "text"],
  ["Notes on file", "notes", "text"],
];

export function CustomerProfile({caseId}: {caseId: number}) {
  const detail = useCareCase(caseId);
  const query = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Partial<Record<EditableCustomerField, string | boolean>>>({});
  const save = useMutation({
    mutationFn: (customerId: number) =>
      apiFetch(`/care/customers/${customerId}`, {method: "PUT", body: JSON.stringify(draft)}),
    onSuccess: () => {
      setEditing(false);
      query.invalidateQueries({queryKey: ["care", "case", caseId]});
    },
  });

  if (caseId == null || !detail.data) {
    return <Card className="text-sm text-muted-foreground">Customer details appear here.</Card>;
  }
  const {customer: c, history, case: kase} = detail.data;
  const allOpened = [kase.opened_at, ...history.map((h) => h.opened_at)].sort();
  const openCount =
    (kase.state !== "closed" ? 1 : 0) + history.filter((h) => h.state !== "closed").length;

  function startEditing() {
    const seed: Partial<Record<EditableCustomerField, string | boolean>> = {};
    for (const [, field, kind] of EDITABLE_FIELDS) {
      seed[field] = kind === "bool" ? !!c[field] : (c[field] as string | null) ?? "";
    }
    save.reset();
    setDraft(seed);
    setEditing(true);
  }

  // Computed/derived facts -- never editable (project rules: no fabricated
  // client facts). Rendered the same read-only way whether or not the
  // editable fields above are currently in edit mode.
  const derived: [string, string | number | null][] = [
    ["Primary platform", c.platform],
    ["Handle", c.handle],
    ["Relationship since", fmtDate(c.customer_since)],
    ["First contact", fmtDate(allOpened[0])],
    ["Last activity", fmtDate(kase.last_activity_at)],
    ["Lifetime cases", history.length + 1],
    ["Open cases", openCount],
    ["Avg CSAT", null],
    ["Sentiment trend", null],
  ];

  return (
    <div className="grid content-start gap-3">
      <div className="flex items-center justify-between">
        <h2 className="m-0 text-sm font-semibold text-muted-foreground">Customer</h2>
        {!editing ? (
          <button type="button" onClick={startEditing}
            className="text-xs font-semibold text-primary hover:underline dark:text-highlight">
            Edit
          </button>
        ) : (
          <span className="flex items-center gap-2">
            <button type="button" disabled={save.isPending} onClick={() => save.mutate(c.id)}
              className="text-xs font-semibold text-primary hover:underline dark:text-highlight disabled:opacity-50">
              Save
            </button>
            <button type="button" disabled={save.isPending} onClick={() => {setEditing(false); save.reset();}}
              className="text-xs text-muted-foreground hover:text-foreground">
              Cancel
            </button>
          </span>
        )}
      </div>
      {c.platform && <ChannelBadge channel={c.platform}/>}
      {save.isError && <p role="alert" className="m-0 text-xs text-danger">{(save.error as Error).message}</p>}

      <dl className="grid gap-1.5 text-[0.8125rem]">
        {EDITABLE_FIELDS.map(([label, field, kind]) => (
          <div key={field} className="grid grid-cols-[minmax(0,110px)_minmax(0,1fr)] items-center gap-2">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="m-0 min-w-0 break-words">
              {!editing ? (
                kind === "bool"
                  ? (c[field] == null ? <span className="text-muted-foreground">unknown</span> : (c[field] ? "Yes" : "No"))
                  : ((c[field] as string | null) || <span className="text-muted-foreground">unknown</span>)
              ) : kind === "bool" ? (
                <input aria-label={label} type="checkbox" checked={!!draft[field]}
                  onChange={(e) => setDraft((d) => ({...d, [field]: e.target.checked}))}/>
              ) : (
                <input aria-label={label} type="text" value={(draft[field] as string) ?? ""}
                  onChange={(e) => setDraft((d) => ({...d, [field]: e.target.value}))}
                  className="w-full rounded-[0.375rem] border bg-card px-1.5 py-0.5 text-[0.8125rem] outline-none focus-visible:ring-2 focus-visible:ring-highlight/40"/>
              )}
            </dd>
          </div>
        ))}
        <div className="my-1 border-t"/>
        {derived.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[minmax(0,110px)_minmax(0,1fr)] gap-2">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="m-0 min-w-0 break-words">
              {value === null || value === undefined || value === ""
                ? <span className="text-muted-foreground">unknown</span>
                : String(value)}
            </dd>
          </div>
        ))}
      </dl>

    </div>
  );
}
