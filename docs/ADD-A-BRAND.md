# Adding a Brand

On this platform a **brand is a workspace**: one *focus brand*, the *competitors*
it's measured against, its match rules, and its own set of source credentials.
Adding a brand means creating a workspace. You do it from the guided wizard;
the Admin page is for editing afterwards.

> All of this requires signing in as an **admin** user.

---

## The wizard (the intended path)

Sidebar → **New workspace** (`/onboarding`). Five steps.

### Step 1 · Workspace

| Field | Notes |
|---|---|
| **Name** | Free text, e.g. `Bank Alfalah`. A URL slug is generated from it. |
| **Market** | Default `PK`. |
| **Volume scenario** | `low` / `mid` / `high` — drives the modelled cost estimate and the X monthly read cap. |
| **Sentiment languages** | Default `en`. Roman Urdu is indexed but not scored until calibrated. |

Creates the workspace and switches your session into it.

### Step 2 · Brands

- **Focus brand** — one name (required).
- **Competitors** — up to 5 names.

Each name is turned into a starter match-rule set automatically. `Bank Alfalah`
becomes:

- `\bbank\s*alfalah\b` (spaced form)
- `\bbankalfalah\b` (joined form)

A **live preview** runs as you type (`/onboarding/preview?name=…`) and shows how
many already-collected items that name would match, with samples — a quick sanity
check that the rule isn't too loose or too tight.

Re-running this step later **replaces the whole brand set** for the workspace.

### Step 3 · Context & excludes

Tighten matching so unrelated chatter doesn't come in.

- **Context terms** — one phrase per line (`car leasing`, `branch`, `ATM`, …).
  Plain phrases are converted to regexes; lines already starting with `\b` are
  used as-is. These are co-occurrence hints, not hard filters.
- **Exclude terms** — one per line as `term — reason` (em dash or ` - `).
  e.g. `Alfalah Insurance — separate entity`. Anything matching an exclude
  pattern is dropped from the focus brand.

### Step 4 · Credentials (per workspace)

Every source key from `apps/api/.env.example` can be entered here — Meta, X,
YouTube, Reddit, Bright Data, DataForSEO, app stores, etc. See the full table in
[REMAINING-WORK.md](REMAINING-WORK.md#1-credentials--accounts--nothing-runs-live-without-these).

- A value entered here is **workspace-scoped** and overrides the shared default.
- Left blank → the workspace inherits the shared key, or the source stays
  "not configured" and simply doesn't collect.

**"App creds for Meta":** `META_ACCESS_TOKEN` + `META_PAGE_ID`
(+ `META_IG_USER_ID` for Instagram). These are Page-specific, so they normally go
**per workspace**, not shared.

### Step 5 · Finish

- Registers the per-source collection schedule (tick) for the workspace.
- **Run now** (checkbox) enqueues a first collection run immediately, with a live
  job console. Otherwise it starts on its normal cadence.

After this the workspace appears in the tenant switcher.

---

## Editing after onboarding — the Admin page

`/admin`, admin only. Relevant sections:

| Section | Use for |
|---|---|
| **Workspaces** | Rename, market, volume scenario, archive. |
| **Brands & rules** | Add/edit/archive individual brands. Add a competitor to an existing brand here (new row, **focus = off**). Each editor has a live match preview. `safe` patterns are one regex per line; `gated` / `exclude` are JSON. |
| **API keys** | Add or change credentials after the fact. Each key is saved either **shared** (default for every workspace) or against **one workspace** (overrides shared there). |
| **Sources** | See which sources are wired, their cadence, and health. |
| **Cost** | Modelled spend for the workspace's volume scenario. |
| **Jobs & runs** | Kick off a collection or scoring run, watch the console, see run history. |

---

## Match-rule vocabulary (quick reference)

| Term | Meaning |
|---|---|
| **safe** | Patterns confident enough to match and surface to a client with no review. |
| **gated** | Patterns that match but hold the item for calibration review before it's client-visible. |
| **context** | Phrases that should co-occur with a brand mention to raise confidence. |
| **exclude** | Patterns that disqualify a match (namesakes, unrelated entities). |
| **is_focus** | Exactly one brand per workspace is the focus; the rest are competitors. |

---

## What won't happen automatically

- **No data collects for a source until its credentials exist.** Add them in
  step 4 or Admin → API keys.
- **Replies / owned analytics / email are still mock-mode platform-wide** — see
  [REMAINING-WORK.md](REMAINING-WORK.md#2-real-http-transports--still-mock-mode-developer-work-your-call-on-scope).
  Onboarding a brand doesn't change that.
