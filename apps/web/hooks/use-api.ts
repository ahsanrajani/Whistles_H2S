"use client";
import {keepPreviousData, useQuery} from "@tanstack/react-query";
import {apiFetch} from "@/lib/api";
import type {ComplianceResult, ContentImpact, ContentInsights, ContentRisk, ContentSignals} from "@/lib/types";
import type {AssignmentRule, AdminBrands, AdminCost, AdminFeatures, AdminKeys, AdminRoles, AdminRuns, AdminSources, AdminUsers, AdminWorkspaces, AlertsPage, Auth, BranchesPage, BranchItemsPage, BranchMapPage, CareAgentReport, CareAgentsList, CareCaseDetail, CareCaseList, CarePending, CarePerformance, CareQueues, CareRoster, CareScheduled, CareSearchResponse, CareSessionHistory, CareSessionState, CareSuggestion, CompetitorsPage, ComplaintReport, ContentCalendar, ContentDetail, CrawlPages, CrawlReport, CsatReport, ImpersonationPage, IncidentsPage, JobsQueue, KbArticleDetail, KbArticles, MacroApplyResult, MacroPreview, MacroRules, Macros, Mentions, MetricCatalog, MetricReport, MisClosedCases, MisDaily, OnboardingState, Overview, OwnedAnalyticsStatus, OwnedComments, OwnedPosts, PrecisionReport, ProductLinesPage, Projects, RegulatoryPage, ReportSchedules, RetentionReport, ReviewQueue, ReviewsPage, RoutingPolicyResp, ScamPage, ScheduledTasksResp, SentimentPage, SeoReport, SeoSuggestions, SeoVisibility, SlaReport, SocialReport, SourceHealthReport, Stats, SwitchIntentPage, ThemesPage, TriagePage, VantageEvidence, VantageInsights, VantagePrompts, Workspaces} from "@/lib/types";

export const useMe = () => useQuery({queryKey: ["me"], queryFn: () => apiFetch<Auth>("/auth/me")});
export const useWorkspaces = () => useQuery({queryKey: ["workspaces"], queryFn: () => apiFetch<Workspaces>("/workspaces")});
export const useProjects = () => useQuery({queryKey: ["projects"], queryFn: () => apiFetch<Projects>("/projects")});

// --- Vantage AI-visibility panel (Phase 5) ---
export const useVantagePrompts = () => useQuery({queryKey: ["vantage", "prompts"], queryFn: () => apiFetch<VantagePrompts>("/vantage/prompts")});
export const useVantageInsights = () => useQuery({queryKey: ["vantage", "insights"], queryFn: () => apiFetch<VantageInsights>("/vantage/insights")});
export const useVantageEvidence = () => useQuery({queryKey: ["vantage", "evidence"], queryFn: () => apiFetch<VantageEvidence>("/vantage/evidence")});
export const useVantageSeo = () => useQuery({queryKey: ["vantage", "seo"], queryFn: () => apiFetch<SeoVisibility>("/vantage/seo")});
export const useSeoReport = () => useQuery({queryKey: ["vantage", "seo", "report"], queryFn: () => apiFetch<SeoReport>("/vantage/seo/report")});
export const useCrawlReport = () => useQuery({queryKey: ["vantage", "seo", "crawl"], queryFn: () => apiFetch<CrawlReport>("/vantage/seo/crawl")});
export const useSeoSuggestions = () => useQuery({queryKey: ["vantage", "seo", "suggestions"], queryFn: () => apiFetch<SeoSuggestions>("/vantage/seo/suggestions")});
export const useCrawlPages = (taskId: string | null, check: string, enabled: boolean) => useQuery({
  queryKey: ["vantage", "seo", "crawl", "pages", taskId, check],
  queryFn: () => apiFetch<CrawlPages>(`/vantage/seo/crawl/pages?task_id=${encodeURIComponent(taskId!)}&check=${encodeURIComponent(check)}`),
  enabled: enabled && !!taskId,
});

// --- Recent owned posts (Meta/LinkedIn/YouTube/X), dashboard widget + grid ---
export const useOwnedPosts = (opts?: {platform?: string; limit?: number}) => useQuery({
  queryKey: ["owned-posts", opts?.platform ?? "all", opts?.limit ?? 25],
  queryFn: () => apiFetch<OwnedPosts>(`/owned-posts?${new URLSearchParams({
    ...(opts?.platform ? {platform: opts.platform} : {}),
    limit: String(opts?.limit ?? 25),
  })}`),
});
export const useOwnedComments = (source: string, postExternalId: string, enabled: boolean) => useQuery({
  queryKey: ["owned-posts", "comments", source, postExternalId],
  queryFn: () => apiFetch<OwnedComments>(`/owned-posts/comments?${new URLSearchParams({source, post_external_id: postExternalId})}`),
  enabled,
});

// --- Social care (F1/F2) ---
export const useCareCases = (tab: string) => useQuery({
  queryKey: ["care", "cases", tab],
  queryFn: () => apiFetch<CareCaseList>(`/care/cases?tab=${encodeURIComponent(tab)}`),
  refetchInterval: 60_000,
});
export const useCareCase = (id: number | null) => useQuery({
  queryKey: ["care", "case", id],
  queryFn: () => apiFetch<CareCaseDetail>(`/care/cases/${id}`),
  enabled: id != null,
  // Hamza: "for a running conversation, 1 minute refresh rate is slow, but
  // fine for incoming messages [in the queue list]" -- an agent actively
  // watching one open thread wants new messages sooner than the list does;
  // the realtime push (useRealtime in console-view.tsx) still delivers
  // instantly when the WS connection is up, this is just the poll floor.
  refetchInterval: id != null ? 8_000 : false,
});
// Auto-loads the moment a case is opened -- server-cached per (case, thread
// state) in core/ai_assist.py, so reopening the same case (or another agent
// opening it) doesn't cost a second real model call unless the thread
// actually changed since. staleTime keeps a remount (e.g. tab refocus) from
// refetching a suggestion the agent is already looking at.
export const useCareSuggestReply = (caseId: number | null, enabled: boolean) => useQuery({
  queryKey: ["care", "case", caseId, "suggest-reply"],
  queryFn: () => apiFetch<CareSuggestion>(`/care/cases/${caseId}/suggest`, {method: "POST", body: JSON.stringify({kind: "reply"})}),
  enabled: enabled && caseId != null,
  staleTime: 60_000,
});
export const useCareAgents = (opts?: {enabled?: boolean}) => useQuery({queryKey: ["care", "agents"], queryFn: () => apiFetch<CareAgentsList>("/care/agents"), enabled: opts?.enabled ?? true});
// Macros: the library is readable by every care role; rules need templates:edit.
export const useMacros = (opts?: {includeInactive?: boolean; enabled?: boolean}) => useQuery({queryKey: ["care", "macros", !!opts?.includeInactive], queryFn: () => apiFetch<Macros>(`/macros${opts?.includeInactive ? "?include_inactive=true" : ""}`), enabled: opts?.enabled ?? true, staleTime: 30_000});
export const useMacroRules = (enabled = true) => useQuery({queryKey: ["care", "macro-rules"], queryFn: () => apiFetch<MacroRules>("/macro-rules"), enabled});
export const previewMacro = (caseId: number, macroId: number) => apiFetch<MacroPreview>(`/care/cases/${caseId}/macros/${macroId}/preview`, {method: "POST"});
export const applyMacro = (caseId: number, macroId: number, indexes?: number[]) => apiFetch<MacroApplyResult>(`/care/cases/${caseId}/macros/${macroId}/apply`, {method: "POST", body: JSON.stringify(indexes ? {indexes} : {})});
export const useKbArticles = (q: string, drafts = false) => useQuery({queryKey: ["kb", "articles", q, drafts], queryFn: () => apiFetch<KbArticles>(`/kb/articles?q=${encodeURIComponent(q)}${drafts ? "&drafts=true" : ""}`)});
export const useKbArticle = (id: number | null) => useQuery({queryKey: ["kb", "article", id], queryFn: () => apiFetch<KbArticleDetail>(`/kb/articles/${id}`), enabled: id != null});
export const useCareScheduled = (id: number | null) => useQuery({queryKey: ["care", "scheduled", id], queryFn: () => apiFetch<CareScheduled>(`/care/cases/${id}/scheduled`), enabled: id != null});
export const useCareSearch = (q: string, enabled = true) => useQuery({queryKey: ["care", "search", q], queryFn: () => apiFetch<CareSearchResponse>(`/care/search?q=${encodeURIComponent(q)}`), enabled: enabled && q.trim().length >= 2, staleTime: 10_000});
// Hamza: "make sure the available/not available/busy/break toggle ...
// works ... all times/activity is logged and displayed" -- the header
// control's own current state (not hardcoded on mount) and its recent
// shift history.
export const useCareSessionState = () => useQuery({queryKey: ["care", "session"], queryFn: () => apiFetch<CareSessionState>("/care/session")});
export const useCareSessionHistory = (enabled: boolean) => useQuery({queryKey: ["care", "session", "history"], queryFn: () => apiFetch<CareSessionHistory>("/care/session/history"), enabled});

// --- Supervisor console (F2) ---
export const useCareRoster = () => useQuery({queryKey: ["care", "roster"], queryFn: () => apiFetch<CareRoster>("/care/roster"), refetchInterval: 15_000});
export const useAssignmentRule = () => useQuery({queryKey: ["care", "assignment-rule"], queryFn: () => apiFetch<AssignmentRule>("/care/assignment-rule"), refetchInterval: 15_000});
export const useCareQueues = () => useQuery({queryKey: ["care", "queues"], queryFn: () => apiFetch<CareQueues>("/care/queues"), refetchInterval: 15_000});
export const useCarePerformance = () => useQuery({queryKey: ["care", "performance"], queryFn: () => apiFetch<CarePerformance>("/care/performance")});
export const useCarePending = () => useQuery({queryKey: ["care", "pending"], queryFn: () => apiFetch<CarePending>("/care/pending"), refetchInterval: 10_000});
export const useCareAgentReport = (start: string, end: string) => useQuery({queryKey: ["reports", "care-agents", start, end], queryFn: () => apiFetch<CareAgentReport>(`/reports/care/agents?start=${start}&end=${end}`)});

// --- Content calendar (F4) ---
export const useContentCalendar = (start: string, end: string, state?: string) => useQuery({queryKey: ["content", "calendar", start, end, state], queryFn: () => apiFetch<ContentCalendar>(`/content?start=${start}&end=${end}${state ? `&state=${state}` : ""}`)});
export const useContentItem = (id: number | null) => useQuery({queryKey: ["content", "item", id], queryFn: () => apiFetch<ContentDetail>(`/content/${id}`), enabled: id != null});
export const useContentRisk = (start: string, end: string) => useQuery({queryKey: ["content", "ai", "risk", start, end], queryFn: () => apiFetch<ContentRisk>(`/content/ai/risk?start=${start}&end=${end}`)});
export const useContentSignals = () => useQuery({queryKey: ["content", "ai", "signals"], queryFn: () => apiFetch<ContentSignals>("/content/ai/signals")});
export const useContentInsights = () => useQuery({queryKey: ["content", "ai", "insights"], queryFn: () => apiFetch<ContentInsights>("/content/ai/insights")});
export const useContentImpact = () => useQuery({queryKey: ["content", "ai", "impact"], queryFn: () => apiFetch<ContentImpact>("/content/ai/impact")});
// A POST-by-design read (the text is the input), cached per exact text so an unchanged draft is never re-checked.
export const useComplianceCheck = (text: string, rewrite: boolean) => useQuery({
  queryKey: ["content", "ai", "compliance", text, rewrite],
  queryFn: () => apiFetch<ComplianceResult>("/content/ai/compliance", {method: "POST", body: JSON.stringify({text, rewrite})}),
  enabled: text.trim().length > 0, staleTime: 60_000,
});

// --- Reports (F5) ---
export const useMetricCatalog = () => useQuery({queryKey: ["reports", "metrics-catalog"], queryFn: () => apiFetch<MetricCatalog>("/reports/metrics/catalog")});
export const useMetricReport = (qs: string, enabled = true) => useQuery({queryKey: ["reports", "metrics", qs], queryFn: () => apiFetch<MetricReport>(`/reports/metrics?${qs}`), enabled});
export const useSlaReport = (start: string, end: string) => useQuery({queryKey: ["reports", "sla", start, end], queryFn: () => apiFetch<SlaReport>(`/reports/sla?start=${start}&end=${end}`)});
export const useSocialReport = (source: string, start: string, end: string, enabled = true) => useQuery({queryKey: ["reports", "social", source, start, end], queryFn: () => apiFetch<SocialReport>(`/reports/social?source=${source}&start=${start}&end=${end}`), enabled});
export const useCsatReport = (start: string, end: string) => useQuery({queryKey: ["reports", "csat", start, end], queryFn: () => apiFetch<CsatReport>(`/reports/csat?start=${start}&end=${end}`)});
export const useComplaintReport = (start: string, end: string) => useQuery({queryKey: ["reports", "complaints", start, end], queryFn: () => apiFetch<ComplaintReport>(`/reports/complaints?start=${start}&end=${end}`)});
export const useMisDaily = (start: string, end: string) => useQuery({queryKey: ["reports", "mis-daily", start, end], queryFn: () => apiFetch<MisDaily>(`/reports/mis/daily?start=${start}&end=${end}`)});
export const useMisClosedCases = (start: string, end: string) => useQuery({queryKey: ["reports", "mis-closed", start, end], queryFn: () => apiFetch<MisClosedCases>(`/reports/mis/closed-cases?start=${start}&end=${end}`)});
export const useReportSchedules = () => useQuery({queryKey: ["reports", "schedules"], queryFn: () => apiFetch<ReportSchedules>("/reports/schedules")});

// --- Admin ops (F6) ---
export const useSourceHealth = () => useQuery({queryKey: ["admin", "source-health"], queryFn: () => apiFetch<SourceHealthReport>("/admin/sources/health"), refetchInterval: 30_000});
export const useRetention = () => useQuery({queryKey: ["admin", "retention"], queryFn: () => apiFetch<RetentionReport>("/admin/retention")});
export const usePrecision = () => useQuery({queryKey: ["admin", "precision"], queryFn: () => apiFetch<PrecisionReport>("/admin/precision")});
export const useOwnedAnalyticsStatus = () => useQuery({queryKey: ["admin", "owned-analytics"], queryFn: () => apiFetch<OwnedAnalyticsStatus>("/admin/owned-analytics")});
export const useRoutingPolicy = () => useQuery({queryKey: ["admin", "routing-policy"], queryFn: () => apiFetch<RoutingPolicyResp>("/admin/routing-policy")});
export const useJobsQueue = () => useQuery({queryKey: ["admin", "jobs-queue"], queryFn: () => apiFetch<JobsQueue>("/admin/jobs/queue"), refetchInterval: 15_000});
export const useScheduledTasks = () => useQuery({queryKey: ["admin", "jobs-scheduled"], queryFn: () => apiFetch<ScheduledTasksResp>("/admin/jobs/scheduled")});
export const useOverview = (query: string) => useQuery({queryKey: ["overview", query], queryFn: () => apiFetch<Overview>(`/overview${query ? `?${query}` : ""}`)});
export const useMentions = (query: string) => useQuery({queryKey: ["mentions", query], queryFn: () => apiFetch<Mentions>(`/mentions${query ? `?${query}` : ""}`)});
export const useSentiment = (query: string) => useQuery({queryKey: ["sentiment", query], queryFn: () => apiFetch<SentimentPage>(`/sentiment${query ? `?${query}` : ""}`)});
export const useCompetitors = (query: string) => useQuery({queryKey: ["competitors", query], queryFn: () => apiFetch<CompetitorsPage>(`/competitors${query ? `?${query}` : ""}`)});
export const useReviews = (query: string) => useQuery({queryKey: ["reviews", query], queryFn: () => apiFetch<ReviewsPage>(`/reviews${query ? `?${query}` : ""}`)});
export const useThemes = () => useQuery({queryKey: ["themes"], queryFn: () => apiFetch<ThemesPage>("/themes")});
export const useScam = (query: string) => useQuery({queryKey: ["scam", query], queryFn: () => apiFetch<ScamPage>(`/scam${query ? `?${query}` : ""}`)});
export const useTriage = (query: string) => useQuery({queryKey: ["triage", query], queryFn: () => apiFetch<TriagePage>(`/triage${query ? `?${query}` : ""}`)});
export const useSwitchIntent = (query: string) => useQuery({queryKey: ["switch-intent", query], queryFn: () => apiFetch<SwitchIntentPage>(`/switch-intent${query ? `?${query}` : ""}`)});
export const useIncidents = () => useQuery({queryKey: ["incidents"], queryFn: () => apiFetch<IncidentsPage>("/incidents")});
export const useProductLines = (query: string) => useQuery({queryKey: ["product-lines", query], queryFn: () => apiFetch<ProductLinesPage>(`/product-lines${query ? `?${query}` : ""}`)});
export const useRegulatory = () => useQuery({queryKey: ["regulatory"], queryFn: () => apiFetch<RegulatoryPage>("/regulatory")});
export const useBranches = (query: string) => useQuery({queryKey: ["branches", query], queryFn: () => apiFetch<BranchesPage>(`/branches${query ? `?${query}` : ""}`)});
export const useBranchItems = (key: string, query: string) => useQuery({queryKey: ["branch-items", key, query], queryFn: () => apiFetch<BranchItemsPage>(`/branches/${encodeURIComponent(key)}/items?${query}`), placeholderData: keepPreviousData});
export const useBranchMap = () => useQuery({queryKey: ["branches-map"], queryFn: () => apiFetch<BranchMapPage>("/branches/map"), staleTime: 10 * 60_000});
export const useImpersonation = () => useQuery({queryKey: ["impersonation"], queryFn: () => apiFetch<ImpersonationPage>("/impersonation"), staleTime: 5 * 60_000});
export const useAlerts = () => useQuery({queryKey: ["alerts"], queryFn: () => apiFetch<AlertsPage>("/alerts"), refetchInterval: 60_000});

export const useAdminWorkspaces = () => useQuery({queryKey: ["admin", "workspaces"], queryFn: () => apiFetch<AdminWorkspaces>("/admin/workspaces")});
export const useAdminBrands = () => useQuery({queryKey: ["admin", "brands"], queryFn: () => apiFetch<AdminBrands>("/admin/brands")});
export const useAdminUsers = () => useQuery({queryKey: ["admin", "users"], queryFn: () => apiFetch<AdminUsers>("/admin/users")});
export const useAdminRoles = () => useQuery({queryKey: ["admin", "roles"], queryFn: () => apiFetch<AdminRoles>("/admin/roles")});
export const useAdminKeys = () => useQuery({queryKey: ["admin", "keys"], queryFn: () => apiFetch<AdminKeys>("/admin/keys")});
export const useAdminSources = () => useQuery({queryKey: ["admin", "sources"], queryFn: () => apiFetch<AdminSources>("/admin/sources")});
export const useAdminFeatures = () => useQuery({queryKey: ["admin", "features"], queryFn: () => apiFetch<AdminFeatures>("/admin/features")});
export const useAdminCost = () => useQuery({queryKey: ["admin", "cost"], queryFn: () => apiFetch<AdminCost>("/admin/cost")});
export const useAdminRuns = () => useQuery({queryKey: ["admin", "runs"], queryFn: () => apiFetch<AdminRuns>("/admin/runs"), refetchInterval: 15_000});
export const useStats = () => useQuery({queryKey: ["stats"], queryFn: () => apiFetch<Stats>("/stats"), refetchInterval: 30_000});
export const useReview = () => useQuery({queryKey: ["review"], queryFn: () => apiFetch<ReviewQueue>("/review")});
export const useOnboarding = () => useQuery({queryKey: ["onboarding"], queryFn: () => apiFetch<OnboardingState>("/onboarding/state")});
