# UX principles and flows

## Principles

1. The URL is state: periods, channels, filters, sorting, and drilldowns survive reload and sharing.
2. Every surface has loading, empty, and error states that explain the next useful action.
3. Numbers retain intervals, sample sizes, progress, ties, or “not estimable.”
4. Each screen has one primary action. Overview investigates; Mentions filters evidence.
5. Keyboard-first navigation starts with Ctrl/Command-K.

## Flows

- **Daily check:** changed strip → KPI grid → ranked actions → charts → evidence. Durable movements link to their evidence slice.
- **Investigate a spike:** a volume point or delta opens `/mentions` with URL-encoded period and brand; the mix describes the slice.
- **Sentiment read:** gauge includes positive share, 95% interval, and scored count. The weekly positive/negative trend retains its sample size, and negative themes deep-link to `?q=<term>&sentiment=neg`.
- **Competitor check:** share rows draw point estimates and Wilson bands; overlapping intervals are called statistically tied. Opportunity outlets deep-link to an outlet-filtered evidence slice.
- **Review read:** distribution and 4-star-or-better Wilson interval establish rating quality before store, trend, theme, and recent-review detail. Review themes deep-link with `surface=app_reviews`.
- **Theme read:** the focus-brand cloud encodes frequency by size and sentiment lean by tone; every term opens a URL-restorable mention search. The table preserves raw positive and negative counts.
- **Triage a flagged match:** admins see Unverified and Hide/Undo inline; inclusion has no approval gate.
- **Configure a workspace:** Phase 3 unifies the wizard and previews corpus matches before save.
- **Run collection/scoring:** Phase 3 adds source status and an SSE console with retained logs.
- **First run:** empty states distinguish no connection, no collection, no scoring, and no filter results.

The command palette covers native pages, switchable workspaces for unpinned admins, and the five most recent URL-backed mention filters stored only in the current browser.
