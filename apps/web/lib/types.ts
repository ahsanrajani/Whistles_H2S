import type {components} from "./api-types";

export type Workspace = {id: number; name: string; market: string; onboarding_step: number; slug: string};
export type User = {id: number; name: string; role: "admin" | "bank_viewer"; roles: string[]; perms: string[]; workspace: Workspace | null; features?: Record<string, boolean>};
export type Auth = {user: User};
export type Workspaces = {active: Workspace | null; can_switch: boolean; list: Workspace[]};
export type Project = {id: number; slug: string; name: string; kind: string};
export type Projects = {projects: Project[]; active: string};

// --- Social care (Phase F1/F2) ---
export type CareSlaState = "ok" | "at_risk" | "breached" | null;
export type CarePriority = "high" | "elevated" | "normal";
export type CareCaseRow = {
  id: number; state: string; channel: string | null; assignee_id: number | null;
  opened_at: string; last_activity_at: string; first_response_at: string | null;
  closed_at: string | null; display_name: string | null; handle: string | null;
  platform: string | null; messages: number;
  waiting_seconds: number; sla_state: CareSlaState; priority: CarePriority;
};
export type CareCaseList = {tab: string; cases: CareCaseRow[]};
export type CareMessage = {
  direction: "inbound" | "outbound"; channel: string; author: string | null;
  body: string; sent_at: string; platform_ref: string | null; permalink: string | null;
};
export type CareNote = {id: number; author_id: number | null; author_username: string | null; body: string; created_at: string};
export type CareEvent = {kind: string; actor: string | null; actor_username: string | null; detail: Record<string, unknown>; at: string};
export type CareCaseRecord = {
  id: number; state: string; channel: string | null; assignee_id: number | null;
  opened_at: string; first_response_at: string | null; closed_at: string | null;
  closure_category: string | null; last_activity_at: string;
};
export type CareCustomer = {
  id: number; display_name: string | null; handle: string | null;
  platform: string | null; email: string | null; phone: string | null;
  customer_since: string | null;
  preferred_name: string | null; other_handles: string | null;
  location: string | null; country: string | null; language: string | null;
  timezone: string | null; segment: string | null; account_status: string | null;
  vip: boolean | null; blocked: boolean | null; preferred_channel: string | null;
  tags: string | null; notes: string | null;
};
// Hamza (Customer panel screenshot): "these details should be editable."
// platform/handle excluded -- the real-customer match key, edited nowhere
// in the UI (see api_fastapi/care.py::update_customer's own comment).
export type EditableCustomerField = Exclude<keyof CareCustomer, "id" | "platform" | "handle" | "customer_since">;
export type CareHistoryCase = {id: number; state: string; channel: string | null; opened_at: string; closed_at: string | null};
export type CareCaseDetail = {
  case: CareCaseRecord;
  customer: CareCustomer;
  messages: CareMessage[]; notes: CareNote[]; timeline: CareEvent[];
  history: CareHistoryCase[];
};
// --- Admin ops (F6) ---
export type SourceHealthEntry = {
  source: string; label: string; surface: string; source_class: string; cadence_seconds: number;
  health: "ok" | "stale" | "failing" | "down" | "unknown"; circuit_state: string;
  consecutive_failures: number; items_last_run: number; last_run_id: string | null;
  last_success_at: string | null; last_attempt_at: string | null; last_error: string | null;
};
export type SourceHealthReport = {sources: SourceHealthEntry[]; unhealthy: SourceHealthEntry[]; counts: Record<string, number>};
export type RetentionReport = {workspace_id: number; policy: Record<string, string>; classes: string[]; modes: string[]};
export type PrecisionEntry = {class: string; matched: number; labelled: number; correct: number; precision: number | null; ci_low: number | null; ci_high: number | null; target: number; met: boolean};
export type PrecisionReport = {brands: {brand: string; safe: PrecisionEntry; gated: PrecisionEntry}[]; sample_size: number; sample_target: number; targets: {safe: number; gated: number}; all_measured_met: boolean};
export type OwnedAnalyticsStatus = {sources: {source: string; facts: number; first_day: string | null; last_day: string | null; metrics: number; last_captured_at: string | null}[]; providers: {platform: string; live: boolean}[]};
export type RoutingPolicyResp = {policy: {first_response_sla: number; resolution_sla: number; escalation_after: number; default_capacity: number}; closure_categories_in_use: string[]};
export type AssignStrategyKey = "manual" | "round_robin" | "least_busy" | "longest_idle";
export type AssignStrategy = {key: AssignStrategyKey; label: string; description: string};
export type AssignmentRule = {strategy: AssignStrategyKey; strategies: AssignStrategy[]; roles: string[]; available_agents: number; free_agents: number; waiting_cases: number; held_back_cases: number};
export type JobsQueue = {by_state: Record<string, number>; dead: {id: number; kind: string; attempts: number; max_attempts: number; last_error: string | null; updated_at: string}[]};
export type ScheduledTasksResp = {scheduled: {id: number; name: string; kind: string; cron: string; tenant_id: number | null; enabled: number; last_run: string | null; next_run: string}[]};

// --- Reports (F5) ---
export type Measure = {kind: "count" | "proportion"; value: number | null; numerator?: number; denominator?: number; wilson?: [number, number]};
export type MetricComparison = {window: {start: string; end: string; days?: number}; previous: number | null; absolute: number | null; pct: number | null; significant?: boolean};
export type MetricSeriesPoint = {day: string} & Partial<Measure>;
export type MetricReport = {
  source: string; metric: string; entity_type: string | null;
  window: {start: string; end: string; days: number};
  measure: Measure; series: MetricSeriesPoint[];
  group_by?: string; groups?: ({key: string} & Measure)[];
  comparison?: MetricComparison;
};
export type MetricCatalogEntry = {source: string; metric: string; entity_type: string; rows: number; first_day: string | null; last_day: string | null; is_proportion: boolean; dims: string[]};
export type MetricCatalog = {metrics: MetricCatalogEntry[]; groupable: string[]};

export type SlaReport = {
  window: {start: string; end: string}; policy: {first_response_sla: number; resolution_sla: number}; cases: number;
  first_response: {compliance: {met: number; eligible: number; rate: number | null; wilson: [number | null, number | null]}; seconds: {n: number; avg: number | null; p50: number | null; p90: number | null; max: number | null}};
  resolution: {compliance: {met: number; eligible: number; rate: number | null; wilson: [number | null, number | null]}};
  assignment_wait: {seconds: {n: number; avg: number | null; p50: number | null; p90: number | null; max: number | null}};
  missed: {total: number; by_check: Record<string, number>};
};

export type SocialPost = {post: string; media_type: string; first_day: string | null; last_day: string | null; impressions: number | null; engagements: number | null; reactions: number | null; engagement_rate: Measure};
export type SocialReport = {
  source: string; window: {start: string; end: string};
  account: Record<string, {measure: Measure; comparison: MetricComparison | null}>;
  posts: SocialPost[]; video: SocialPost[]; reels: SocialPost[];
  engagement_by_media_type: ({media_type: string} & Measure)[];
};

export type CsatReport = {
  window: {start: string; end: string}; issued: number; responses: number;
  response_rate: {rate: number | null; wilson: [number | null, number | null]; n: number; k: number};
  csat: {rate: number | null; wilson: [number | null, number | null]; n: number; k: number};
  nps: number | null; avg_score: number | null; distribution: Record<string, number>;
  by_channel: Record<string, {rate: number | null; wilson: [number | null, number | null]; n: number; k: number}>;
  comments: {score: number | null; bucket: string | null; comment: string | null}[];
};
export type ComplaintReport = {
  window: {start: string; end: string}; total: number; closed: number; open: number;
  reopen_rate: {rate: number | null; wilson: [number | null, number | null]; n: number; k: number};
  avg_resolution_seconds: number | null; avg_csat: number | null;
  by_category: Record<string, number>; by_channel: Record<string, number>; daily_volume: Record<string, number>;
};

export type MisDaily = {window: {start: string; end: string}; daily: {day: string; opened: number; closed: number; reopened: number}[]; totals: {opened: number; closed: number; reopened: number}};
export type MisClosedCases = {window: {start: string; end: string}; headers: string[]; count: number; rows: Record<string, string | number | null>[]};

export type ReportSchedule = {id: number; name: string; kind: string; format: string; params: Record<string, unknown>; cron: string; recipients: string[]; active: boolean; last_run_at: string | null; last_status: string | null};
export type ReportSchedules = {schedules: ReportSchedule[]};

// --- Content calendar (F4) ---
export type ContentState = "draft" | "in_review" | "approved" | "rejected" | "scheduled" | "published";
export type ContentListItem = {
  id: number; title: string; channel: string | null; state: ContentState;
  scheduled_for: string | null; assigned_to: number | null; approved_by: number | null;
  published_at: string | null; updated_at: string;
};
export type ContentCalendar = {window: {start: string; end: string}; items: ContentListItem[]};
export type ContentItemFull = {
  id: number; workspace_id: number; title: string; body: string; channel: string | null;
  media: string[]; scheduled_for: string | null; state: ContentState;
  created_by: number | null; assigned_to: number | null; approved_by: number | null;
  approved_at: string | null; published_at: string | null; outbound_action_id: number | null;
  created_at: string; updated_at: string;
};
export type ContentEvent = {actor: string | null; kind: string; note: string | null; detail: Record<string, unknown>; at: string};
export type ContentDetail = {item: ContentItemFull; history: ContentEvent[]};
export type ContentMediaUpload = {url: string; filename: string; content_type: string; size: number};

export type BranchComplaintUploadResult = {
  inserted: number; skipped: number;
  errors: {row: number; reason: string}[];
  job_id: string | null;
};
export type ContentSuggestion = {caption: string; hashtags: string[]; mock: boolean};

// --- Content intelligence: compliance, signals, insights, impact ---
export type ComplianceSeverity = "high" | "review" | "note" | "clear";
export type ComplianceFinding = {key: string; label: string; weight: number; matches: string[]; guidance: string; topic: string};
export type ComplianceNotice = {id: number; regulator: string; title: string; url: string | null; published_at: string | null; topics: string[]};
export type ComplianceResult = {
  score: number; severity: ComplianceSeverity; findings: ComplianceFinding[];
  awareness_context: boolean; checked_chars: number;
  related_notices: ComplianceNotice[];
  rewrite: {text: string; mock: boolean; error?: string} | null;
  policy: {rules: {key: string; label: string; weight: number; topic: string}[]; bands: {key: string; label: string; min_score: number}[]};
};
export type ContentRisk = {risk: Record<string, {severity: ComplianceSeverity; score: number}>};

export type RateInterval = {k: number; n: number; rate: number | null; ci_low: number | null; ci_high: number | null};
export type ContentNudge = {
  key: string; kind: "scam" | "incident" | "regulatory"; severity: "high" | "elevated" | "watch";
  title: string; why: string; evidence: Record<string, unknown>; topic: string; draft: string;
  links: {label: string; url: string}[];
};
export type ContentSignals = {nudges: ContentNudge[]};
export type ContentDraftFromSignal = {id: number; title: string; mock: boolean; compliance: {severity: ComplianceSeverity; score: number; flags: string[]}};

export type InsightPost = {
  platform: string; url: string | null; published_at: string | null; text: string;
  engagement: number | null; vs_baseline: number | null; band: "above" | "typical" | "below" | null;
  topics: string[]; scammers_working_it: boolean;
  comments: {n: number; scam_flagged: RateInterval | null; complaints: RateInterval | null} | null;
};
export type TimingBucket = {label: string; posts: number; ratio: number | null};
export type ContentInsights = {
  baseline: {median_engagement: number | null; posts_with_metrics: number; needed: number; note: string | null};
  posts: InsightPost[];
  topics: {key: string; label: string; posts: number; avg_engagement: number | null; complaints: RateInterval | null}[];
  timing: {available: boolean; tz: string; posts: number; note?: string; by_weekday?: TimingBucket[]; by_daypart?: TimingBucket[]; best_weekday?: TimingBucket | null; best_daypart?: TimingBucket | null};
  digest: {kind: "risk" | "win" | "topic" | "timing" | "empty"; text: string; url?: string | null}[];
};
export type ImpactVerdict = "improved" | "no_durable_change" | "worse" | "too_early" | "not_enough_data";
export type ContentImpact = {
  window_days: number; min_comments: number; min_elapsed_days: number; note: string;
  summary: {improved: number; no_durable_change: number; worse: number; pending: number};
  items: {id: number; title: string; channel: string | null; published_at: string; from_signal: string | null; metric: string; measures: string; before: RateInterval; after: RateInterval; verdict: ImpactVerdict; reason: string}[];
};

export type CareSearchResult = {type: "case" | "customer" | "message"; id: number; case_id: number | null; label: string; detail: string | null; score: number};
export type CareSearchResponse = {query: string; results: CareSearchResult[]};
export type CareAgent = {user_id: number; username: string; capacity: number; available: number; live: number};
export type CareAgentsList = {agents: CareAgent[]};
export type CareRosterAgent = CareAgent & {presence: "online" | "idle" | "offline" | "unknown"; seconds_ago?: number};
export type CareRoster = {agents: CareRosterAgent[]};
export type CareSessionState = {state: "ready" | "not_ready" | "idle" | "active"; reason: string | null; at: string | null};
export type CareSessionEvent = {kind: string; at: string; reason: string | null};
export type CareSessionHistory = {events: CareSessionEvent[]};
export type CareQueueRow = {channel: string | null; unassigned: number; open: number; oldest_waiting_s: number; at_risk: number; breached: number};
export type CareQueues = {queues: CareQueueRow[]};
export type CarePerfAgent = {user_id: number; username: string; assigned: number; closed: number; avg_first_response_s: number | null; avg_handle_s: number | null; sla_breaches: number};
export type CarePerfSummary = {open_cases: number; closed_cases: number; avg_first_response_s: number | null; avg_handle_s: number | null};
export type CarePerformance = {summary: CarePerfSummary; agents: CarePerfAgent[]};
export type CarePendingRow = {id: number; platform: string; action: string; target_ref: string | null; request: {text?: string; case_id?: number} | null; actor: string | null; created_at: string};
export type CarePending = {pending: CarePendingRow[]};
export type CareAgentReportRow = {user_id: number; username: string | null; session_seconds: number; ready_seconds: number; not_ready_seconds: number; idle_seconds: number; logins: number; cases_touched: number; cases_closed: number; avg_first_response_seconds: number | null; avg_handle_seconds: number | null; occupancy: number | null};
export type CareAgentReport = {window: {start: string; end: string}; agents: CareAgentReportRow[]};
export type CareSuggestion = {kind: string; suggestion: string; sources: number[]; mock: boolean; cached: boolean};
export type CareScheduledMsg = {outbound_action_id: number; text: string; scheduled_for: string | null; created_at: string | null};
export type CareScheduled = {scheduled: CareScheduledMsg[]};

// --- Macros (0035): canned reply + case actions; quick = pinned to the Send menu
export type MacroStatus = "open" | "assigned" | "in_progress" | "internal_hold" | "pending_approval" | "closed";
export type MacroPriority = "low" | "normal" | "high" | "urgent";
export type MacroAction =
  | {type: "set_status"; status: MacroStatus; closure_category?: string}
  | {type: "assign"; mode: "self" | "agent" | "auto"; user_id?: number}
  | {type: "add_note"; body: string}
  | {type: "set_priority"; priority: MacroPriority}
  | {type: "add_tags"; tags: string[]};
export type Macro = {
  id: number; name: string; category: string; body: string; shortcut: string | null;
  description: string | null; is_quick: boolean; quick_order: number; actions: MacroAction[];
  active: boolean; updated_at: string; rule_count?: number;
};
export type Macros = {macros: Macro[]};
export type MacroPreview = {
  macro_id: number; name: string; text: string; actions: (MacroAction & {summary: string})[];
};
export type MacroActionResult = {index: number; type: string; ok: boolean; error?: string};
export type MacroApplyResult = {ok: boolean; results: MacroActionResult[]};
export type MacroTrigger =
  | {type: "new_case"} | {type: "sla_breach"}
  | {type: "no_response"; minutes: number} | {type: "unassigned_for"; minutes: number}
  | {type: "keyword"; words: string[]};
export type MacroReplyMode = "none" | "hold" | "send";
export type MacroRule = {
  id: number; name: string; active: boolean; macro_id: number; macro_name: string;
  triggers: MacroTrigger[]; filters: {channels?: string[]; vip_only?: boolean};
  reply_mode: MacroReplyMode; last_fired_at: string | null; fired_count: number;
};
export type MacroRules = {rules: MacroRule[]; trigger_types: string[]; reply_modes: string[]};
export type KbArticleRow = {id: number; title: string; tags: string; published: boolean; created_by: number | null; updated_at: string; attachments: number};
export type KbArticles = {articles: KbArticleRow[]};
export type KbArticleDetail = {article: {id: number; title: string; body: string; tags: string; published: boolean; updated_at: string}; attachments: {id: number; filename: string; url: string; created_at: string}[]};
export type Delta = {now: number | null; prior: number | null; pct: number | null; dir: "up" | "down"};
export type Stat = {key: string; label: string; value: string; sub: string; delta: number | null; href: string};
export type Action = {tone: "risk" | "watch" | "opportunity" | "ok"; tag: string; title: string; body: string; stat?: string; action?: {label: string; href: string}};
export type MixCategory = {key: string; label: string; colour: string; n: number; pct: number; pos: number; neu: number; neg: number; delta_pct: number | null};
export type Mix = {total: number; cats: MixCategory[]};
export type Sov = {id: number; name: string; focus: boolean; n: number; review: number; excluded: number; p: number; lo: number; hi: number; total: number};
export type VantagePrompt = {id: number; prompt_text: string; active: boolean; created_at: string};
export type VantagePrompts = {prompts: VantagePrompt[]};
export type VantageBrand = {name: string; is_focus: boolean; rate: number | null; wilson: [number | null, number | null]; n: number; k: number};
export type VantageGap = {prompt_id: number; model: string; day: string; competitors_named: string[]};
export type VantageInsights = {total_responses: number; failed_calls: number; brands: VantageBrand[]; visibility_gaps: VantageGap[]; headline: string[]; improvements: string[]; confused_responses: number; uncertain_responses: number};
export type VantageRunQueued = {ok: boolean; job_id: string; already: boolean};
export type VantageMention = {brand_id: number; name: string; is_focus: boolean; rule: string; excluded: boolean};
export type VantageFlag = "possible_wrong_entity" | "uncertain";
export type VantageEvidenceRow = {id: number; prompt_id: number; prompt_text: string; provider: string; model: string; day: string; response_text: string; mentions: VantageMention[]; error: string | null; flags: VantageFlag[]};
export type VantageEvidence = {responses: VantageEvidenceRow[]};

export type OwnedPostPlatform = "facebook" | "instagram" | "linkedin" | "youtube" | "x";
export type OwnedPostMetrics = {likes?: number | null; comments?: number | null; shares?: number | null; views?: number | null; reposts?: number | null; replies?: number | null; quotes?: number | null};
export type OwnedPostMedia =
  | {type: "photo"; image: string}
  | {type: "video"; video?: string; image?: string}
  | {type: "youtube"; video_id: string; image?: string};
export type OwnedPost = {platform: OwnedPostPlatform; platform_label: string; source: string; external_id: string | null; url: string | null; author: string | null; published_at: string | null; title: string | null; body: string | null; metrics: OwnedPostMetrics | null; media: OwnedPostMedia | null};
export type OwnedPosts = {posts: OwnedPost[]};
export type OwnedComment = {external_id: string; url: string | null; author: string | null; published_at: string | null; body: string | null; kind: "comment" | "reply"; parent_id: string | null};
export type OwnedComments = {comments: OwnedComment[]};

export type SeoDomain = {domain: string; best_rank: number; appearances: number; sample_url: string | null};
export type SeoBrand = {id: number; name: string; is_focus: boolean; own_domains: SeoDomain[]};
export type SeoVisibility = {brands: SeoBrand[]; third_party: SeoDomain[]; total_domains: number; total_results: number};

export type SeoKeyword = {keyword: string; rank: number | null; search_volume: number | null; url: string | null};
export type SeoBacklinks = {backlinks?: number; referring_domains?: number; referring_main_domains?: number; rank?: number};
export type SeoReportBrand = {id: number; name: string; is_focus: boolean; keywords: SeoKeyword[]; backlinks: SeoBacklinks};
export type SeoReport = {day: string | null; brands: SeoReportBrand[]};
export type SeoRunResult = {ok: boolean; keywords_pulled: number; backlinks_pulled: number; facts_written: number; errors: string[]; day: string; log: string[]};

export type CrawlBrand = {id: number; name: string; is_focus: boolean; onpage_score: number | null; pages_crawled: number | null; task_id: string | null; checks: Record<string, number>; cwv: Record<string, number>; scores: Record<string, number>};
export type CrawlReport = {day: string | null; brands: CrawlBrand[]};
export type CrawlRunQueued = {ok: boolean; job_id: string; already: boolean};
export type CrawlPage = {url: string | null; status_code: number | null};
export type CrawlPages = {pages: CrawlPage[]};

export type SeoSuggestionItem = {priority: "HIGH" | "MEDIUM" | "LOW"; text: string};
export type SeoSuggestion = {id: number; provider: string; model: string; raw_text: string; suggestions: SeoSuggestionItem[]; error: string | null; created_at: string};
export type SeoSuggestions = {suggestion: SeoSuggestion | null};
export type Theme = {term: string; n: number; neg: number; pos: number; lean: string};
export type SentimentBrand = {id: number; name: string; focus: boolean; pos: number; neu: number; neg: number; scored: number; not_scored: number; pending: number; neg_share: number | null; neg_lo: number | null; neg_hi: number | null};
export type Gauge = {track: string; segs: {cls: string; d: string}[]; pos_pct: number; lo: number; hi: number; pos: number; neu: number; neg: number; scored: number; name: string; vb_h: number} | null;
export type TopicVolume = {axis: string[]; days: number; peak: number; raw_peak?: number; window?: number; peak_day: string | null; series: {name: string; focus: boolean; color: string; total: number; points: string; area: string | null; counts: number[]; smooth?: number[]}[]; vw: number; vh: number};
export type SentimentTrend = {axis: string[]; pos: (number | null)[]; neg: (number | null)[]; n: number[]; pos_points: string; neg_points: string; has_data: boolean};
export type ReviewTrend = {axis: string[]; avg: (number | null)[]; n: number[]; points: string; has_data: boolean};
export type Mention = {id: number; brand_id: number; brand: string; surface: string; source: string; source_kind: string; outlet: string | null; author: string | null; published_at: string | null; collected_at: string; collection_run_id: string | null; url: string | null; text: string; rule: string; needs_review: number; sampled: number; language: string | null; sentiment: string | null; rating: number | null; type: string | null; hidden: number; other_brands: string | null};
export type FeedItem = {id: number; brand: string; surface: string; source: string; outlet: string | null; published_at: string | null; url: string | null; text: string; rule: string; needs_review: number; language: string | null; sampled: number; sentiment: string | null; type: string | null};
export type Priority = {key: string; severity: "critical" | "warning" | "info"; title: string; detail: string; href: string; when: string | null};
export type Overview = {period: string; period_label: string; channel: string; channels: string[]; focus: Sov | null; kpis: Stat[]; deltas: Record<string, Delta>; cards: Action[]; priorities: Priority[]; report_ready: boolean; gauge: Gauge; topic_volume: TopicVolume; mix: Mix; sov: Sov[]; pairs: [string, string][]; reviews: null | {stores: {store: string; n: number; avg: number; dist: number[]}[]; dist: number[]; overall_n: number; overall_avg: number; good_share: number; good_lo: number; good_hi: number; recent: {store: string; rating: number; when: string; text: string; url: string}[]}; themes: Theme[]; feed: FeedItem[]; admin: null | {ledger: Record<string, unknown>[]; rules: Record<string, unknown>[]; exclusions: [string, number][]}};
export type Mentions = {rows: Mention[]; total: number; mix: Mix; filters: Record<string, string | number | null>; facets: {brands: {id: number; name: string}[]; surfaces: string[]; outlets: string[]; categories: {key: string; label: string}[]}; is_admin: boolean; source_meta: Record<string, {label: string; surface: string}>};
export type SentimentPage = {period: string; period_label: string; focus: Sov | null; gauge: Gauge; trend: SentimentTrend; breakdown: SentimentBrand[]; deltas: Record<string, Delta>; neg_themes: Theme[]; neg_feed: FeedItem[]};
export type OpportunityGap = {outlet: string; total: number; brands: [string, number][]};
export type CompetitorsPage = {period: string; period_label: string; focus: Sov | null; sov: Sov[]; pairs: [string, string][]; gaps: OpportunityGap[]; gap_total: number; reached: number; total_outlets: number; deltas: Record<string, Delta>; trend: TopicVolume; outlets: {name: string; n: number}[]};
export type ReviewData = {stores: {store: string; n: number; avg: number; dist: number[]; recent: {rating: number; when: string; text: string; url: string | null; app: {id: string; name: string | null; icon: string | null} | null}[]}[]; dist: number[]; overall_n: number; overall_avg: number; good_share: number; good_lo: number; good_hi: number; recent: {store: string; rating: number; when: string; text: string; url: string | null; app: {id: string; name: string | null; icon: string | null} | null}[]};
export type RatingTimeline = {axis: string[]; roll_avg: (number | null)[]; roll_n: number[]; roll_share: Record<"1" | "2" | "3" | "4" | "5", (number | null)[]>; window: number; days: number; has_data: boolean};
export type ReviewsPage = {focus_brand_id: number | null; store_stats: components["schemas"]["ReviewStoreStats"] | null; period: string; period_label: string; reviews: ReviewData | null; deltas: Record<string, Delta>; trend: ReviewTrend; timeline: RatingTimeline; themes: Theme[]};
export type ThemesPage = {focus: Sov | null; cloud: Theme[]; table: Theme[]};

// ---- Comment scam / brand-abuse signals ----
export type ScamSeverity = "high" | "elevated" | "low" | "clear";
export type ScamSignalRule = {key: string; label: string; weight: number};
export type ScamSignalCount = ScamSignalRule & {n: number};
export type ScamBand = {key: ScamSeverity; label: string; min_score: number};
export type ScamFlag = {id: number; brand: string | null; surface: string; source: string; outlet: string | null; author_ref: string | null; published_at: string | null; url: string | null; text: string; score: number; severity: ScamSeverity; signals: string[]; repeat: boolean};
export type ScamOffender = {actor_ref: string; comments: number; flagged: number; score_sum: number; max_score: number; max_severity: ScamSeverity; surfaces: string[]; signals: string[]; sample: string; repeat: boolean};
export type ScamPage = {
  period: string; period_label: string; channel: string; surface: string;
  coverage: {scanned: number; with_actor_id: number; sources: string[]; note: string};
  policy: {signals: ScamSignalRule[]; bands: ScamBand[]; max_score: number};
  summary: {scanned: number; flagged: number; flag_rate: number; high: number; elevated: number; low: number; repeat_offenders: number};
  signals: ScamSignalCount[];
  flagged: ScamFlag[];
  flagged_total: number;
  offenders: ScamOffender[];
};

// ---- Complaint severity triage ----
export type TriageBandKey = "critical" | "high" | "elevated" | "watch" | "routine";
export type TriageRule = {key: string; label: string; weight: number; kind: "text" | "context"};
export type TriageRuleCount = TriageRule & {n: number};
export type TriageBand = {key: TriageBandKey; label: string; min_score: number};
export type TriageCase = {id: number; brand: string | null; focus: boolean; surface: string; source: string; outlet: string | null; author: string | null; published_at: string | null; url: string | null; text: string; rating: number | null; sentiment: string | null; type: string | null; needs_review: number; score: number; band: TriageBandKey; signals: string[]};
export type TriageBrand = {brand: string | null; focus: boolean; scanned: number; flagged: number; high: number};
export type TriagePage = {
  period: string; period_label: string;
  coverage: {scanned: number; focus_brand: string | null; note: string};
  policy: {signals: TriageRule[]; bands: TriageBand[]; max_score: number};
  summary: {scanned: number; flagged: number; critical: number; high: number; elevated: number; watch: number; focus_flagged: number};
  signals: TriageRuleCount[];
  queue: TriageCase[];
  queue_total: number;
  by_brand: TriageBrand[];
};

// ---- Switch-intent detection ----
export type SwitchBandKey = "high" | "likely" | "watch" | "none";
export type SwitchRule = {key: string; label: string; weight: number; kind: "text" | "context"};
export type SwitchRuleCount = SwitchRule & {n: number};
export type SwitchBand = {key: SwitchBandKey; label: string; min_score: number};
export type SwitchCase = {id: number; surface: string; source: string; outlet: string | null; author: string | null; published_at: string | null; url: string | null; text: string; rating: number | null; sentiment: string | null; type: string | null; score: number; band: SwitchBandKey; signals: string[]; competitor_named: boolean};
export type SwitchIntentPage = {
  period: string; period_label: string;
  coverage: {scanned: number; focus_brand: string | null; competitors: string[]; note: string};
  policy: {signals: SwitchRule[]; bands: SwitchBand[]; max_score: number};
  summary: {scanned: number; flagged: number; high: number; likely: number; watch: number};
  signals: SwitchRuleCount[];
  queue: SwitchCase[];
  queue_total: number;
};

// ---- Competitor incident detection ----
export type IncidentStatus = "incident" | "elevated" | "normal";
export type IncidentDay = {date: string; count: number; z: number};
export type IncidentSample = {id: number; outlet: string | null; url: string | null; text: string};
export type Incident = {date: string; count: number; z: number; baseline_mean: number; keyword_share: number; keywords: string[]; gated_in: boolean; sample: IncidentSample[]};
export type IncidentBrand = {
  brand: string; focus: boolean;
  baseline: {mean: number; stdev: number; days: number};
  recent: IncidentDay[]; series: IncidentDay[];
  peak_z: number; incidents: Incident[]; status: IncidentStatus;
};
export type IncidentsPage = {
  params: {lookback_days: number; baseline_days: number; recent_days: number; z_threshold: number; min_count: number; keyword_share: number; stdev_floor: number};
  as_of: string; axis: string[]; lexicon: string[];
  brands: IncidentBrand[]; incident_count: number; elevated_count: number;
};

// ---- Product-line share of voice ----
export type ProductLineSample = {id: number; outlet: string | null; url: string | null; published_at: string | null; sentiment: string | null; text: string};
export type ProductLine = {key: string; label: string; keywords: string[]; n: number; share: number; pos: number; neu: number; neg: number; scored: number; neg_share: number | null; neg_lo: number | null; neg_hi: number | null; sample: ProductLineSample[]};
export type ProductLinesPage = {
  period: string; period_label: string;
  coverage: {focus_brand: string | null; total: number; classified: number; unclassified: number; multi_line: number};
  policy: {lines: {key: string; label: string; keywords: string[]}[]};
  lines: ProductLine[];
  other: {n: number; share: number};
};

// ---- Regulatory watch ----
export type RegulatoryTopic = {key: string; label: string; keywords: string[]};
export type RegulatoryNotice = {id: number; regulator: string; url: string | null; published_at: string | null; title: string; summary: string; topics: string[]; brands: string[]; names_focus: boolean};
export type RegulatoryPage = {
  focus_brand: string | null;
  policy: {topics: RegulatoryTopic[]};
  total: number;
  regulators: {name: string; n: number}[];
  topics: {key: string; label: string; n: number}[];
  brand_hits: {brand: string; n: number}[];
  notices: RegulatoryNotice[];
};

// ---- Impersonation / brand-abuse watch ----
export type ImpersonationBandKey = "high" | "elevated" | "watch" | "none";
export type ImpersonationDns = "resolves" | "nxdomain" | "unknown";
export type ImpersonationCandidate = {domain: string; technique: string; dns: ImpersonationDns; ct_observed: boolean; score: number; band: ImpersonationBandKey};
export type ImpersonationPage = {
  official: string[];
  policy: {techniques: {key: string; label: string; weight: number}[]; bands: {key: ImpersonationBandKey; label: string; min_score: number}[]; resolves_bonus: number; ct_bonus: number};
  ct_status: "ok" | "unavailable" | "skipped";
  summary: {candidates: number; resolving: number; ct_observed: number; dns_checked: number; high: number; elevated: number; watch: number};
  candidates: ImpersonationCandidate[];
};

// ---- Branch & ATM performance ----
export type BranchBandKey = "high" | "elevated" | "watch" | "none";
export type BranchIssue = {key: string; label: string; n: number};
export type BranchSample = {id: number; surface: string; source: string; outlet: string | null; url: string | null; published_at: string | null; rating: number | null; sentiment: string | null; issue: string | null; text: string};
export type BranchRow = {
  key: string; name: string; code: string; city: string;
  reviews: number; mean_rating: number | null;
  neg_review_share: number | null; neg_review_lo: number | null; neg_review_hi: number | null;
  rating_recent: number | null; rating_prev: number | null; rating_delta: number | null;
  social: number; neg: number; neg_share: number | null;
  complaints: number; critical: number;
  issues: BranchIssue[]; top_issue: string | null;
  score: number; band: BranchBandKey; last_flag_at: string | null; samples: BranchSample[];
};
export type BranchesPage = {
  period: string; period_label: string;
  policy: {issues: {key: string; label: string}[]; bands: {key: BranchBandKey; label: string; min_score: number}[]; min_reviews: number; recent_days: number};
  coverage: {focus_brand: string | null; branches: number; reviews: number; social_matched: number; unresolved_social: number};
  summary: {branches_flagged: number; high: number; elevated: number; reviews: number; mean_rating: number | null};
  branches: BranchRow[];
};
export type BranchItem = Omit<BranchSample, "issue"> & {category: string | null; issues: string[]};
export type BranchItemsPage = {
  branch: {key: string; name: string; code: string; city: string} | null;
  issue: string | null; period: string; policy: BranchesPage["policy"];
  total: number; offset: number; limit: number; items: BranchItem[];
};
export type BranchMapPoint = {
  code: string; name: string; city: string; address: string;
  lat: number; lng: number; has_atm: boolean;
  kind?: string; precision?: string | null;  // set only for a workspace's own `location` rows
  google_rating?: number | null; google_reviews?: number | null;  // the listing's own overall figures; null = not captured
  key: string | null; band: BranchBandKey; score: number;
  mean_rating: number | null; reviews: number; complaints: number; critical: number;
  top_issue: string | null; last_flag_at: string | null;
};
export type BranchMapPage = {
  focus_brand: string | null;
  branches: BranchMapPoint[];
  summary: {total: number; flagged: number};
};

// ---- Anomaly alerting ----
export type AlertSeverity = "critical" | "warning";
export type AlertRule = {key: string; severity: AlertSeverity; title: string; value: number; threshold: number; fired: boolean; href: string; detail: string};
export type AlertsPage = {
  config: Record<string, number | boolean>;
  alerts: AlertRule[];
  firing: AlertRule[];
  counts: {rules: number; firing: number; critical: number; warning: number};
};
export type AlertDispatchResult = {sent: string[]; errors: {channel: string; error: string}[]; firing: number; text: string};

// ---- Admin (Phase 3) ----
export type AdminWorkspace = {id: number; name: string; market: string; volume_scenario: string};
export type AdminWorkspaces = {active_id: number; list: AdminWorkspace[]};
export type BrandRule = {id: number; name: string; is_focus: boolean; active: boolean; safe_patterns: string[]; gated_patterns: Record<string, string>; context_patterns: string[]; exclude_patterns: (string | [string, string])[]};
export type AdminBrands = {ws_id: number; brands: BrandRule[]};
export type BrandPreview = {errors: {group: string; pattern: string; error: string}[]; sample_size: number; match_count: number; excluded_count: number; matched: {id: number; text: string; outlet: string | null; surface: string; rule: string; needs_review: boolean; excluded: boolean; reason: string | null}[]};
export type AdminUser = {id: number; username: string; role: string; active: boolean; workspace: string | null; workspace_id: number | null};
export type AdminUsers = {users: AdminUser[]; workspaces: {id: number; name: string}[]};
export type AdminRole = {key: string; label: string; rank: number};
export type AdminRoles = {roles: AdminRole[]};
export type WorkspaceKey = {env_var: string; label: string; value: string | null};
export type SharedKey = {env_var: string; label: string; value: string | null; status: string; note: string | null; from_env: boolean};
export type AdminKeys = {ws_id: number; ws_name: string | null; workspace: WorkspaceKey[]; shared: SharedKey[]};
export type AdminSource = {id: string; label: string; surface: string; kind: string; unit: string; unit_cost: number; cost_note: string; warn: string | null; client_safe: boolean; enabled: boolean};
export type AdminSources = {sources: AdminSource[]};
export type AdminFeature = {key: string; kind: "surface" | "module" | "cap"; label: string; enabled: boolean};
export type AdminFeatures = {features: AdminFeature[]};
export type MeasuredCost = {source: string; label: string; calls: number; units: number; spend: number; fails: number; unit_cost: number; unit: string; note: string};
export type AdminCost = {scenario: string; measured: MeasuredCost[]; model: {total: number; detail: Record<string, number>}};
export type RunRow = {id: string; started_at: string; finished_at: string | null; state: string; new_items: number | null};
export type AdminRuns = {runs: RunRow[]};
export type JobStatus = {state: string; lines: string[]};
export type Stats = {items: number; mentions: number; last_run: string | null};

// ---- Review queue (Phase 3) ----
export type CalibrationRow = {rule: string; n: number; gated: boolean; labelled: number; correct: number; target: number; remaining: number; met: boolean; precision: number | null; lo: number | null; hi: number | null};
export type ReviewMention = {brand: string; surface: string; source: string; outlet: string | null; published_at: string | null; url: string | null; text: string; rule: string; needs_review: number; language: string | null; sampled: number; id: number};
export type ReviewQueue = {calibration: CalibrationRow[]; batch: ReviewMention[]};

// ---- Onboarding wizard (Phase 3) ----
export type OnboardingSource = {id: string; label: string; surface: string; needs: string[]};
export type OnboardingState = {
  step: number;
  steps: string[];
  workspace: {id: number; name: string; market: string; volume_scenario: string; sentiment_langs: string} | null;
  key_labels: {var: string; label: string}[];
  sources: {auto: OnboardingSource[]; connect: OnboardingSource[]};
  brands?: {focus: string; competitors: string[]};
  query?: {context_text: string; exclude_text: string};
  connected?: string[];
};
