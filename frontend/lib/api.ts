export type ResearcherFact = {
  id: string;
  fact_type: string;
  value: string;
  confidence: number;
  source_url?: string | null;
  evidence_snippet?: string | null;
  verified: boolean;
  approval_origin: string;
};

export type FactCandidate = {
  id: string;
  researcher_id: string;
  source_document_id?: string | null;
  fact_type: string;
  value: string;
  confidence: number;
  evidence_snippet?: string | null;
  source_url?: string | null;
  status: string;
  origin: string;
  review_note?: string | null;
  reviewed_at?: string | null;
  created_at: string;
};

export type ReviewFact = FactCandidate & {
  researcher_name: string;
};

export type ReviewQueueFilters = {
  status?: string;
  fact_type?: string;
  min_confidence?: string;
  source_contains?: string;
  researcher_id?: string;
};

export type ResearcherIdentity = {
  id: string;
  provider: string;
  external_id: string;
  canonical_name: string;
  profile_url?: string | null;
  match_confidence: number;
  ranking_percentile?: number | null;
  ranking_label?: string | null;
  metadata_json: Record<string, unknown>;
  synced_at: string;
};

export type SourceDocument = {
  id: string;
  researcher_id: string;
  url: string;
  discovered_from_url?: string | null;
  content_type?: string | null;
  checksum?: string | null;
  fetch_status: string;
  http_status?: number | null;
  title?: string | null;
  metadata_json: Record<string, unknown>;
  fetched_at?: string | null;
  created_at: string;
};

export type Researcher = {
  id: string;
  name: string;
  normalized_name: string;
  home_institution?: string | null;
  repec_rank?: number | null;
  birth_month?: number | null;
  facts: ResearcherFact[];
};

export type TalkEvent = {
  id: string;
  source_name: string;
  title: string;
  speaker_name: string;
  speaker_affiliation?: string | null;
  city: string;
  country: string;
  starts_at: string;
  ends_at?: string | null;
  url: string;
};

export type TripCluster = {
  id: string;
  researcher_id: string;
  start_date: string;
  end_date: string;
  itinerary: Array<{
    title: string;
    city: string;
    country: string;
    starts_at: string;
    url: string;
    source_name: string;
  }>;
  opportunity_score: number;
  uses_unreviewed_evidence: boolean;
  rationale: Array<{ label: string; points: number; detail: string }>;
};

export type HostCalendarEvent = {
  id: string;
  title: string;
  location?: string | null;
  starts_at: string;
  ends_at?: string | null;
  url: string;
  metadata_json: Record<string, unknown>;
};

export type OpenSeminarWindow = {
  id: string;
  starts_at: string;
  ends_at: string;
  source: string;
  metadata_json: Record<string, unknown>;
};

export type MatchedOpenWindow = OpenSeminarWindow & {
  fit_type: string;
  distance_days: number;
  within_scoring_window: boolean;
};

export type CostShareEstimate = {
  baseline_round_trip_chf: number;
  multi_city_incremental_chf: number;
  estimated_savings_chf: number;
  roi_percent: number;
  nearest_itinerary_city: string;
  nearest_distance_km: number;
  recommended_mode: string;
  recommendation: string;
  assumption_notes: string[];
  slot_starts_at?: string | null;
};

export type OpportunityCard = {
  cluster: TripCluster;
  researcher: Researcher;
  best_window?: MatchedOpenWindow | null;
  cost_share?: CostShareEstimate | null;
  itinerary_cities: string[];
  draft_ready: boolean;
  draft_blockers: string[];
  draft_count: number;
  latest_draft_id?: string | null;
  latest_draft_template?: string | null;
};

export type OpportunityWorkbench = {
  opportunities: OpportunityCard[];
  host_events: HostCalendarEvent[];
  open_windows: OpenSeminarWindow[];
};

export type ResearcherDetail = Researcher & {
  talk_events: TalkEvent[];
  trip_clusters: TripCluster[];
  identities: ResearcherIdentity[];
  documents: SourceDocument[];
  fact_candidates: FactCandidate[];
};

export type DailyCatch = {
  recent_events: TalkEvent[];
  top_clusters: TripCluster[];
};

export type IngestResponse = {
  source_counts: Record<string, number>;
  created_count: number;
  updated_count: number;
};

export type JobRunResponse = {
  processed_count: number;
  created_count: number;
  updated_count: number;
};

export type CalendarOverlay = {
  host_events: HostCalendarEvent[];
  open_windows: OpenSeminarWindow[];
};

export type SourceHealth = {
  source_name: string;
  source_type: string;
  status: string;
  page_count: number;
  event_count: number;
  samples: string[];
  error?: string | null;
  checked_at: string;
};

export type SourceHealthRecord = SourceHealth & {
  id: string;
  created_at: string;
};

export type SourceReliability = {
  source_name: string;
  source_type: string;
  latest_status: string;
  latest_event_count: number;
  previous_event_count?: number | null;
  checks_recorded: number;
  success_rate: number;
  average_event_count: number;
  trend: string;
  needs_attention: boolean;
  attention_reason?: string | null;
  latest_checked_at: string;
};

export type RunbookStep = {
  key: string;
  title: string;
  status: string;
  detail: string;
  href: string;
  cta_label: string;
  count: number;
};

export type OperatorRunbook = {
  source_attention_count: number;
  pending_fact_count: number;
  draft_ready_opportunity_count: number;
  open_window_count: number;
  host_event_count: number;
  draft_counts_by_status: Record<string, number>;
  recommended_steps: RunbookStep[];
};

export type SeminarSlotTemplate = {
  id: string;
  label: string;
  weekday: number;
  start_time: string;
  end_time: string;
  timezone: string;
  active: boolean;
};

export type SeminarSlotOverride = {
  id: string;
  start_at: string;
  end_at: string;
  status: string;
  reason?: string | null;
};

export type OutreachDraft = {
  id: string;
  researcher_id: string;
  trip_cluster_id: string;
  subject: string;
  body: string;
  status: string;
  blocked_reason?: string | null;
  metadata_json: {
    template_key?: string;
    template_label?: string;
    used_facts?: Array<{
      id: string;
      fact_type: string;
      value: string;
      confidence: number;
      source_url?: string | null;
      evidence_snippet?: string | null;
      approval_origin?: string;
      approved_at?: string | null;
    }>;
    candidate_slot?: {
      id: string;
      starts_at: string;
      ends_at: string;
      source: string;
      metadata_json: Record<string, unknown>;
    } | null;
    cost_share?: CostShareEstimate | null;
    itinerary?: TripCluster["itinerary"];
    checklist?: Array<{
      label: string;
      status: string;
      detail: string;
    }>;
    send_brief?: Array<{
      label: string;
      detail: string;
    }>;
    status_history?: Array<{
      from: string;
      to: string;
      note?: string | null;
      changed_at: string;
    }>;
  };
  created_at: string;
};

export type OutreachDraftListItem = OutreachDraft & {
  researcher_name: string;
  researcher_home_institution?: string | null;
  cluster_start_date: string;
  cluster_end_date: string;
  cluster_score: number;
  template_label?: string | null;
};

export type EnrichResearcherPayload = {
  cv_text?: string | null;
  source_url?: string | null;
  evidence_snippet?: string | null;
  repec_rank?: number | null;
  phd_institution?: string | null;
  nationality?: string | null;
  home_institution?: string | null;
  birth_month?: number | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
const API_ACCESS_TOKEN = process.env.NEXT_PUBLIC_API_ACCESS_TOKEN;

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(API_ACCESS_TOKEN ? { "x-atg-api-key": API_ACCESS_TOKEN } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Fall back to the generic status text when the response body is not JSON.
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function getDailyCatch(): Promise<DailyCatch> {
  return getJson<DailyCatch>("/dashboard/daily-catch");
}

export function getCalendarOverlay(): Promise<CalendarOverlay> {
  return getJson<CalendarOverlay>("/calendar/overlay?rebuild=true");
}

export function getSourceHealth(): Promise<SourceHealth[]> {
  return getJson<SourceHealth[]>("/source-health");
}

export function getSourceHealthHistory(): Promise<SourceHealthRecord[]> {
  return getJson<SourceHealthRecord[]>("/source-health/history");
}

export function getSourceReliability(): Promise<SourceReliability[]> {
  return getJson<SourceReliability[]>("/source-health/reliability");
}

export function getOperatorRunbook(): Promise<OperatorRunbook> {
  return getJson<OperatorRunbook>("/operator/runbook");
}

export function getOpportunityWorkbench(): Promise<OpportunityWorkbench> {
  return getJson<OpportunityWorkbench>("/opportunities/workbench");
}

export function getResearchers(): Promise<Researcher[]> {
  return getJson<Researcher[]>("/researchers");
}

export function getResearcher(id: string): Promise<ResearcherDetail> {
  return getJson<ResearcherDetail>(`/researchers/${id}`);
}

export function getResearcherDocuments(id: string): Promise<SourceDocument[]> {
  return getJson<SourceDocument[]>(`/researchers/${id}/documents`);
}

export async function enrichResearcher(id: string, payload: EnrichResearcherPayload): Promise<Researcher> {
  return getJson<Researcher>(`/researchers/${id}/enrich`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getReviewQueue(filters: ReviewQueueFilters = {}): Promise<ReviewFact[]> {
  const params = new URLSearchParams();
  params.set("status", filters.status || "pending");
  if (filters.fact_type) {
    params.set("fact_type", filters.fact_type);
  }
  if (filters.min_confidence) {
    params.set("min_confidence", filters.min_confidence);
  }
  if (filters.source_contains) {
    params.set("source_contains", filters.source_contains);
  }
  if (filters.researcher_id) {
    params.set("researcher_id", filters.researcher_id);
  }
  return getJson<ReviewFact[]>(`/review/facts?${params.toString()}`);
}

export function getSeminarTemplates(): Promise<SeminarSlotTemplate[]> {
  return getJson<SeminarSlotTemplate[]>("/seminar/templates");
}

export function getSeminarOverrides(): Promise<SeminarSlotOverride[]> {
  return getJson<SeminarSlotOverride[]>("/seminar/overrides");
}

export function getDraft(id: string): Promise<OutreachDraft> {
  return getJson<OutreachDraft>(`/outreach-drafts/${id}`);
}

export function getDrafts(status?: string): Promise<OutreachDraftListItem[]> {
  return getJson<OutreachDraftListItem[]>(status ? `/outreach-drafts?status=${encodeURIComponent(status)}` : "/outreach-drafts");
}

export async function createDraft(researcherId: string, tripClusterId: string, templateKey = "concierge"): Promise<OutreachDraft> {
  return getJson<OutreachDraft>("/outreach-drafts", {
    method: "POST",
    body: JSON.stringify({ researcher_id: researcherId, trip_cluster_id: tripClusterId, template_key: templateKey }),
  });
}

export async function updateDraftStatus(
  draftId: string,
  status: string,
  options: { note?: string; checklist_confirmations?: string[]; send_confirmed?: boolean } = {},
): Promise<OutreachDraft> {
  return getJson<OutreachDraft>(`/outreach-drafts/${draftId}/status`, {
    method: "PATCH",
    body: JSON.stringify({
      status,
      note: options.note ?? null,
      checklist_confirmations: options.checklist_confirmations ?? [],
      send_confirmed: options.send_confirmed ?? false,
    }),
  });
}

export async function runExternalIngest(): Promise<IngestResponse> {
  return getJson<IngestResponse>("/jobs/ingest", {
    method: "POST",
  });
}

export async function runKofCalendarSync(): Promise<IngestResponse> {
  return getJson<IngestResponse>("/jobs/sync-kof-calendar", {
    method: "POST",
  });
}

export async function runSourceAudit(): Promise<SourceHealthRecord[]> {
  return getJson<SourceHealthRecord[]>("/jobs/audit-sources", {
    method: "POST",
  });
}

export async function runRepecSync(researcherId?: string): Promise<JobRunResponse> {
  return getJson<JobRunResponse>("/jobs/repec-sync", {
    method: "POST",
    body: JSON.stringify({ researcher_id: researcherId ?? null }),
  });
}

export async function runBiographerRefresh(researcherId?: string): Promise<JobRunResponse> {
  return getJson<JobRunResponse>("/jobs/biographer-refresh", {
    method: "POST",
    body: JSON.stringify({ researcher_id: researcherId ?? null }),
  });
}

export async function approveFactCandidate(candidateId: string, mergedValue?: string): Promise<FactCandidate> {
  return getJson<FactCandidate>(`/review/facts/${candidateId}/approve`, {
    method: "POST",
    body: JSON.stringify({ merged_value: mergedValue ?? null }),
  });
}

export async function rejectFactCandidate(candidateId: string, note?: string): Promise<FactCandidate> {
  return getJson<FactCandidate>(`/review/facts/${candidateId}/reject`, {
    method: "POST",
    body: JSON.stringify({ note: note ?? null }),
  });
}

export async function createTemplate(payload: {
  label: string;
  weekday: number;
  start_time: string;
  end_time: string;
  timezone: string;
  active: boolean;
}): Promise<SeminarSlotTemplate> {
  return getJson<SeminarSlotTemplate>("/seminar/templates", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateTemplate(
  templateId: string,
  payload: {
    label: string;
    weekday: number;
    start_time: string;
    end_time: string;
    timezone: string;
    active: boolean;
  },
): Promise<SeminarSlotTemplate> {
  return getJson<SeminarSlotTemplate>(`/seminar/templates/${templateId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteTemplate(templateId: string): Promise<void> {
  await getJson<void>(`/seminar/templates/${templateId}`, {
    method: "DELETE",
  });
}

export async function createOverride(payload: {
  start_at: string;
  end_at: string;
  status: string;
  reason?: string;
}): Promise<SeminarSlotOverride> {
  return getJson<SeminarSlotOverride>("/seminar/overrides", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateOverride(
  overrideId: string,
  payload: {
    start_at: string;
    end_at: string;
    status: string;
    reason?: string;
  },
): Promise<SeminarSlotOverride> {
  return getJson<SeminarSlotOverride>(`/seminar/overrides/${overrideId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteOverride(overrideId: string): Promise<void> {
  await getJson<void>(`/seminar/overrides/${overrideId}`, {
    method: "DELETE",
  });
}
