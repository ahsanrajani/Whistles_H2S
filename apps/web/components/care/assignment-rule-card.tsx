"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {Check, Info} from "lucide-react";
import {useAssignmentRule, useMe} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {can} from "@/lib/permissions";
import {cn} from "@/lib/utils";
import type {AssignStrategy, AssignStrategyKey, AssignmentRule} from "@/lib/types";
import {ErrorState} from "@/components/states";
import {Card} from "@/components/ui/card";

/** Supervisor Roster tab: which rule hands a new case to the next agent. Each
 * choice explains itself on hover / keyboard focus (wording comes from the API,
 * so it is written once); the selected rule's text is also always shown below,
 * because touch screens have no hover. */
export function AssignmentRuleCard() {
  const query = useQueryClient();
  const me = useMe();
  const rule = useAssignmentRule();
  const canEdit = can(me.data?.user.perms, "care:approve");

  const choose = useMutation({
    mutationFn: (strategy: AssignStrategyKey) =>
      apiFetch<AssignmentRule>("/care/assignment-rule", {method: "PUT", body: JSON.stringify({strategy})}),
    onSuccess: (data) => {
      query.setQueryData(["care", "assignment-rule"], data);
      query.invalidateQueries({queryKey: ["care", "queues"]});
    },
  });

  if (rule.error) return <ErrorState message={rule.error.message}/>;
  const data = rule.data;
  if (!data) return <Card className="h-44 animate-pulse" aria-busy="true" aria-label="Loading assignment rule"/>;

  // Show the choice immediately while the request is in flight.
  const active = choose.isPending ? choose.variables : data.strategy;
  const current = data.strategies.find((s) => s.key === active);

  return (
    <Card className="space-y-4" data-testid="assignment-rule">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">Auto-assignment</h2>
          {/* <p className="mt-0.5 text-xs text-muted-foreground">
            A new case goes to the next agent by this rule. Only agents are picked — never a supervisor or team lead — and only while
            they are available and under capacity.
          </p> */}
        </div>
        <p className="numeric text-xs text-muted-foreground" aria-live="polite">
          {data.available_agents} available · {data.free_agents} with room · <span className={cn(data.waiting_cases > 0 && "font-semibold text-warning")}>{data.waiting_cases} waiting</span>
          {data.held_back_cases > 0 && (
            <span title="Unassigned before the rule was last set. They stay in the queue for a person to pick up; auto-assignment only handles cases that arrive after the rule is set.">
              {" · "}{data.held_back_cases} older left unassigned
            </span>
          )}
        </p>
      </div>

      <div role="radiogroup" aria-label="Assignment rule" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {data.strategies.map((s) => (
          <RuleOption key={s.key} option={s} selected={s.key === active} disabled={!canEdit || choose.isPending}
            onSelect={() => s.key !== active && choose.mutate(s.key)}/>
        ))}
      </div>

      {current && <p className="text-xs leading-relaxed text-muted-foreground" data-testid="assignment-rule-description"><span className="font-medium text-foreground">{current.label}:</span> {current.description}</p>}
      {choose.error && <p role="alert" className="text-xs text-danger">{choose.error.message}</p>}
      {!canEdit && <p className="text-xs text-muted-foreground">Only a supervisor or team lead can change the rule.</p>}
    </Card>
  );
}

function RuleOption({option, selected, disabled, onSelect}: {option: AssignStrategy; selected: boolean; disabled: boolean; onSelect: () => void}) {
  const tipId = `assign-tip-${option.key}`;
  return (
    <div className="group relative">
      <button type="button" role="radio" aria-checked={selected} aria-describedby={tipId} disabled={disabled} onClick={onSelect}
        className={cn(
          "flex h-full w-full items-center justify-between gap-2 rounded-[0.625rem] border px-3 py-2.5 text-left text-sm transition-colors",
          selected ? "border-primary bg-primary/10 font-medium" : "hover:bg-muted",
          disabled && !selected && "opacity-60",
        )}>
        <span>{option.label}</span>
        {selected ? <Check size={14} aria-hidden className="shrink-0 text-primary"/> : <Info size={13} aria-hidden className="shrink-0 text-muted-foreground"/>}
      </button>
      <div id={tipId} role="tooltip"
        className="pointer-events-none absolute inset-x-0 top-full z-20 mt-1.5 rounded-[0.625rem] border bg-card p-3 text-xs leading-relaxed text-muted-foreground opacity-0 shadow-lg motion-safe:transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
        <span className="mb-1 block font-medium text-foreground">{option.label}</span>
        {option.description}
      </div>
    </div>
  );
}
