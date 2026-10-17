# Bright Data validation gate

Bright Data is reserved for the focus brand's owned Facebook and Instagram channels. It must
not be used for competitor collection. Production ingestion stays disabled until a one-record
probe confirms that the live dataset fields are useful and the account-specific cost is known.

## Credential

Put the token in the ignored `.env`; never pass it on the command line or commit it:

```dotenv
BRIGHT_DATA_API_KEY=replace-with-a-rotated-token
```

Tokens shared in chat should be treated as exposed and rotated after the validation.

## Bounded Facebook probe

Start with one known public post. The probe uses Bright Data's asynchronous
trigger/progress/snapshot workflow with exactly one input and normally one returned post
record:

```powershell
python scripts/probe_bright_data.py "https://www.facebook.com/BankAlfalahOfficial/posts/..."
```

Comments are a separate paid dataset and may return an uncapped number of records. Run this
only on a low-comment post after checking the account's price per record:

```powershell
python scripts/probe_bright_data.py "https://www.facebook.com/BankAlfalahOfficial/posts/..." --include-comments --accept-variable-record-cost
```

The probe prints only coverage/readiness aggregates. It does not save or echo comment bodies.
`meaningful_for_ingestion=true` requires stable post provenance/text/time fields and, when
comments are requested, adequate comment text and actor identity for hashed repeat-offender
tracking.

## Live validation — 1 September 2026

The bounded probe ran against one public Bank Alfalah Facebook post. The successful post-only
snapshot returned one record with complete post ID, URL, text, timestamp, and engagement
fields. The successful post-plus-comments snapshot returned one post and five comments. All
five comments had comment ID, post URL, text, timestamp, and a stable `user_id` or `user_url`;
one matched the phone/WhatsApp/short-link candidate rule. No returned record exposed parent
reply linkage, so nested-thread support remains unverified.

Both reports returned `meaningful_for_ingestion=true`; comment identity coverage was sufficient
for one-way hashed repeat-offender tracking. No raw response was saved. Check the Bright Data
account usage ledger before setting a dollar cap: unsuccessful synchronous attempts timed out
client-side and may still appear in provider billing even though their records were not used.

## Promotion gate

Before adding the production collector:

1. Record the account-specific price per successful post/comment record and define a monthly
   dollar cap.
2. Confirm the official focus-brand page URL and test one low-comment post.
3. Preserve source URL, provider record ID, collection timestamp, and raw JSON in ingestion.
4. Add a hard pre-request monthly cap; never rely on a warning after spend occurs.
5. Implement Facebook posts first and commit independently. Facebook comments follow; then
   Instagram, each in its own commit.

## Shared cost guardrail

`core/collector.py::_bright_data_month_budget` turns the configured caps plus month-to-date
`call_log` usage (summed by `run_collection` across every `brightdata_*` source) into one
record budget shared by all Facebook and Instagram collectors. Keys, despite the `_FACEBOOK_`
in one name: `BRIGHT_DATA_FACEBOOK_MONTHLY_RECORD_CAP` (account-wide record cap),
`BRIGHT_DATA_MONTHLY_CAP_USD` (account-wide dollar cap), `BRIGHT_DATA_COST_PER_RECORD_USD`.
Nothing affordable ⇒ `QuotaExceeded`, which fails the whole run.

## Collectors shipped

- **Facebook posts** (`brightdata_facebook_posts`) — `discover_facebook_page_posts` against
  one configured owned-page username. Per-run limit + shared monthly budget.
- **Instagram posts** (`brightdata_instagram_posts`) — `discover_instagram_profile_posts`
  against one configured owned-profile username; `BRIGHT_DATA_INSTAGRAM_USERNAME` +
  `BRIGHT_DATA_INSTAGRAM_PER_RUN_LIMIT`. **Dataset id `gd_lk5ns7kz21pck8jpis` and
  `discover_by=user_name` are from Bright Data's published catalogue, not yet confirmed on
  this account — first real run must use a tiny `BRIGHT_DATA_MONTHLY_CAP_USD`.**
- **Facebook / Instagram comments** (`brightdata_facebook_comments` /
  `brightdata_instagram_comments`) — one `_BrightDataComments` base, network-specific
  subclasses. Keyed off post URLs already collected by the matching posts adapter (injected
  by `run_collection` as `_BRIGHT_DATA_{FACEBOOK,INSTAGRAM}_POST_URLS`), so **comments lag
  posts by one collection cycle**. Uncapped datasets — bounded by the shared budget +
  `*_COMMENT_POSTS_PER_RUN` + `*_COMMENTS_PER_POST` (`limit_records` to the provider *and*
  re-applied client-side). `raw_json` keeps `post_url`, `parent_comment_id`, and a one-way
  `actor_hash`. IG comments dataset id `gd_ltppn085pokosxh13` is unconfirmed on this account.
- **Facebook comments** (`brightdata_facebook_comments`) — `collect_facebook_post_comments`
  keyed off post URLs already collected by the posts collector (read from the DB by
  `run_collection`; comments therefore lag posts by one collection cycle). The provider's
  comment dataset has **no per-request record cap**, so spend is bounded four ways: the shared
  monthly record cap, the shared monthly USD cap, `BRIGHT_DATA_FACEBOOK_COMMENT_POSTS_PER_RUN`,
  and `BRIGHT_DATA_FACEBOOK_COMMENTS_PER_POST` (sent to the provider as `limit_records` per
  input *and* re-applied to the returned rows). Actor identity is stored one-way hashed
  (`raw_json.actor_hash`) for repeat-offender tracking; the raw provider record is retained
  alongside it. `limit_records` support is assumed from Bright Data's common convention and is
  **not** verified against this account — run one collection with a tiny
  `BRIGHT_DATA_MONTHLY_CAP_USD` and confirm the returned record count before raising caps.
