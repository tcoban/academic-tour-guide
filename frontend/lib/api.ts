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
  travel_fit_score: number;
  travel_fit_label?: string | null;
  travel_fit_summary?: string | null;
  travel_fit_severity: string;
  planning_warnings: string[];
  travel_fit: Record<string, unknown>;
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

export type OpportunityAutonomyAction = {
  label: string;
  consequence: string;
  href?: string | null;
  action_key?: string | null;
  disabled_reason?: string | null;
};

export type OpportunityAutonomySignal = {
  label: string;
  status: string;
  confidence: number;
  detail: string;
  evidence: string[];
};

export type OpportunityAutonomyAssessment = {
  level: string;
  score: number;
  summary: string;
  can_prepare_draft: boolean;
  can_build_tour_leg: boolean;
  can_search_evidence: boolean;
  can_refresh_prices: boolean;
  requires_human_approval: boolean;
  signals: OpportunityAutonomySignal[];
  next_action: OpportunityAutonomyAction;
  moonshot_actions: OpportunityAutonomyAction[];
};

export type OpportunityCard = {
  cluster: TripCluster;
  researcher: Researcher;
  best_window?: MatchedOpenWindow | null;
  cost_share?: CostShareEstimate | null;
  itinerary_cities: string[];
  draft_ready: boolean;
  draft_blockers: string[];
  draft_blocker_details: Array<{
    code: string;
    fact_type?: string | null;
    label: string;
    message: string;
    action_label: string;
    action_href: string;
    pending_candidate_id?: string | null;
  }>;
  draft_count: number;
  latest_draft_id?: string | null;
  latest_draft_template?: string | null;
  tour_leg_count: number;
  latest_tour_leg_id?: string | null;
  route_review_required: boolean;
  route_review_resolved: boolean;
  route_review_action?: {
    label: string;
    href?: string | null;
    action_key: string;
    trip_cluster_id?: string | null;
    explanation: string;
    disabled_reason?: string | null;
  } | null;
  automation_assessment?: OpportunityAutonomyAssessment | null;
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
  official_url?: string | null;
  parser_strategy?: string | null;
  needs_adapter: boolean;
  action_label?: string | null;
  action_href?: string | null;
  consequence?: string | null;
  disabled_reason?: string | null;
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
  last_event_count: number;
  previous_event_count?: number | null;
  checks_recorded: number;
  success_rate: number;
  average_event_count: number;
  trend: string;
  needs_attention: boolean;
  attention_reason?: string | null;
  latest_checked_at?: string | null;
  last_success_at?: string | null;
  latest_error?: string | null;
  official_url?: string | null;
  parser_strategy?: string | null;
  needs_adapter: boolean;
  action_label?: string | null;
  action_href?: string | null;
  consequence?: string | null;
  disabled_reason?: string | null;
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

export type OperatorAction = {
  label: string;
  href?: string | null;
  method: string;
  action_key?: string | null;
  disabled_reason?: string | null;
};

export type OperatorPrimaryFlow = OperatorAction & {
  consequence: string;
};

export type OperatorSetupBlocker = {
  id: string;
  title: string;
  explanation: string;
  action: OperatorPrimaryFlow;
  count: number;
};

export type OperatorTask = {
  id: string;
  group: string;
  severity: string;
  status: string;
  title: string;
  explanation: string;
  primary_action: OperatorAction;
  secondary_actions: OperatorAction[];
  entity_type?: string | null;
  entity_id?: string | null;
  count: number;
  disabled_reason?: string | null;
  last_updated_at?: string | null;
  metadata_json: Record<string, unknown>;
};

export type OperatorTaskGroup = {
  key: string;
  title: string;
  purpose: string;
  tasks: OperatorTask[];
};

export type OperatorCockpit = {
  generated_at: string;
  posture: string;
  posture_detail: string;
  data_state: "empty" | "demo" | "real" | "stale";
  setup_blockers: OperatorSetupBlocker[];
  primary_flow: OperatorPrimaryFlow;
  summary_metrics: Record<string, number>;
  next_best_action?: OperatorTask | null;
  groups: OperatorTaskGroup[];
  recent_changes: AuditEvent[];
  source_snapshot: {
    last_sync_at?: string | null;
    sources_tracked: number;
    sources_checked: number;
    sources_with_events: number;
    sources_needing_attention: number;
    needs_adapter: number;
    total_events_last_check: number;
    latest_issues: Array<{
      source_name: string;
      status: string;
      reason?: string | null;
      official_url?: string | null;
    }>;
  };
};

export type MorningSweepStep = {
  key: string;
  title: string;
  status: string;
  detail: string;
  processed_count: number;
  created_count: number;
  updated_count: number;
  source_counts: Record<string, number>;
  error?: string | null;
};

export type MorningSweepResponse = {
  started_at: string;
  finished_at: string;
  status: string;
  steps: MorningSweepStep[];
  summary_metrics: Record<string, number>;
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

export type Institution = {
  id: string;
  name: string;
  city?: string | null;
  country?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  metadata_json: Record<string, unknown>;
};

export type SpeakerProfile = {
  id: string;
  researcher_id: string;
  topics: string[];
  fee_floor_chf?: number | null;
  notice_period_days?: number | null;
  travel_preferences: Record<string, unknown>;
  rider: Record<string, unknown>;
  availability_notes?: string | null;
  communication_preferences: Record<string, unknown>;
  consent_status: string;
  verification_status: string;
  created_at: string;
  updated_at: string;
};

export type InstitutionProfile = {
  id: string;
  institution_id: string;
  wishlist_topics: string[];
  procurement_notes?: string | null;
  po_threshold_chf?: number | null;
  grant_code_support: boolean;
  coordinator_contacts: Array<Record<string, unknown>>;
  av_notes?: string | null;
  hospitality_notes?: string | null;
  host_quality_score?: number | null;
  created_at: string;
  updated_at: string;
};

export type WishlistEntry = {
  id: string;
  institution_id: string;
  researcher_id?: string | null;
  speaker_name?: string | null;
  topic?: string | null;
  priority: number;
  status: string;
  notes?: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type WishlistAlert = {
  id: string;
  wishlist_entry_id: string;
  researcher_id?: string | null;
  trip_cluster_id?: string | null;
  status: string;
  match_reason: string;
  score: number;
  metadata_json: Record<string, unknown>;
  created_at: string;
  resolved_at?: string | null;
  researcher_name?: string | null;
  institution_name?: string | null;
};

export type WishlistMatchParticipant = {
  id: string;
  match_group_id: string;
  masked_label: string;
  distance_km?: number | null;
  distance_band: string;
  role: string;
  status: string;
  budget_status: string;
  slot_status: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type WishlistMatchGroup = {
  id: string;
  researcher_id?: string | null;
  normalized_speaker_name: string;
  display_speaker_name: string;
  status: string;
  radius_km: number;
  score: number;
  anonymity_mode: string;
  rationale: Array<Record<string, unknown>>;
  metadata_json: Record<string, unknown>;
  participant_count: number;
  participants: WishlistMatchParticipant[];
  created_at: string;
  updated_at: string;
};

export type TourStop = {
  id: string;
  tour_leg_id: string;
  institution_id?: string | null;
  open_window_id?: string | null;
  sequence: number;
  city: string;
  country?: string | null;
  starts_at?: string | null;
  format: string;
  fee_chf: number;
  travel_share_chf: number;
  status: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type TourLeg = {
  id: string;
  researcher_id: string;
  trip_cluster_id?: string | null;
  title: string;
  status: string;
  start_date: string;
  end_date: string;
  estimated_fee_total_chf: number;
  estimated_travel_total_chf: number;
  cost_split_json: Record<string, unknown>;
  rationale: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
  stops: TourStop[];
};

export type TravelPriceCheck = {
  id: string;
  tour_leg_id?: string | null;
  cache_key: string;
  origin_city: string;
  destination_city: string;
  departure_at?: string | null;
  travel_class: string;
  fare_policy: string;
  provider: string;
  status: string;
  amount?: number | null;
  currency: string;
  amount_chf: number;
  confidence: number;
  source_url?: string | null;
  action_href?: string | null;
  raw_summary: Record<string, unknown>;
  error?: string | null;
  fetched_at: string;
  expires_at: string;
  created_at: string;
};

export type TourAssemblyProposal = {
  id: string;
  match_group_id: string;
  researcher_id?: string | null;
  tour_leg_id?: string | null;
  speaker_draft_id?: string | null;
  title: string;
  status: string;
  term_sheet_json: Record<string, unknown>;
  budget_summary_json: Record<string, unknown>;
  blockers: Array<Record<string, unknown>>;
  masked_summary_json: {
    speaker?: string;
    participant_count?: number;
    participants?: Array<Record<string, unknown>>;
    ordered_stops?: Array<Record<string, unknown>>;
  } & Record<string, unknown>;
  match_group?: WishlistMatchGroup | null;
  created_at: string;
  updated_at: string;
};

export type RelationshipBrief = {
  id: string;
  researcher_id: string;
  institution_id: string;
  summary: string;
  communication_preferences: Record<string, unknown>;
  decision_patterns: Record<string, unknown>;
  relationship_history: Array<Record<string, unknown>>;
  operational_memory: Record<string, unknown>;
  forward_signals: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type FeedbackSignal = {
  id: string;
  researcher_id: string;
  institution_id: string;
  tour_leg_id?: string | null;
  party: string;
  signal_type: string;
  value: string;
  sentiment_score?: number | null;
  notes?: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type AuditEvent = {
  id: string;
  event_type: string;
  actor_type: string;
  actor_id?: string | null;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type BusinessCaseResult = {
  id: string;
  run_id: string;
  researcher_id?: string | null;
  case_key: string;
  display_name: string;
  target_name: string;
  verdict: string;
  score: number;
  data_found: boolean;
  kof_fit_status: string;
  route_status: string;
  evidence_status: string;
  draft_status: string;
  price_status: string;
  evidence_summary_json: Record<string, unknown>;
  fit_summary_json: Record<string, unknown>;
  route_summary_json: Record<string, unknown>;
  price_summary_json: Record<string, unknown>;
  draft_gate_json: Record<string, unknown>;
  blockers: Array<{
    code: string;
    title: string;
    explanation: string;
    action_label: string;
    action_href: string;
    consequence: string;
  }>;
  source_links_json: Array<{
    type: string;
    label: string;
    url: string;
  }>;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type BusinessCaseRun = {
  id: string;
  mode: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  summary_json: Record<string, unknown>;
  error?: string | null;
  created_at: string;
  results: BusinessCaseResult[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";
const API_ACCESS_TOKEN = process.env.NEXT_PUBLIC_ROADSHOW_API_ACCESS_TOKEN ?? process.env.NEXT_PUBLIC_API_ACCESS_TOKEN;

export class RoadshowApiError extends Error {
  status?: number;
  unavailable: boolean;

  constructor(message: string, options: { status?: number; unavailable?: boolean } = {}) {
    super(message);
    this.name = "RoadshowApiError";
    this.status = options.status;
    this.unavailable = options.unavailable ?? false;
  }
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(API_ACCESS_TOKEN ? { "x-atg-api-key": API_ACCESS_TOKEN } : {}),
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (cause) {
    throw new RoadshowApiError(
      "Roadshow API is unavailable. Contact the operator or check service status.",
      { unavailable: true },
    );
  }
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
    throw new RoadshowApiError(detail, { status: response.status });
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function getDailyCatch(): Promise<DailyCatch> {
  return getJson<DailyCatch>("/dashboard/daily-catch");
}

export function getCalendarOverlay(options: { rebuild?: boolean } = {}): Promise<CalendarOverlay> {
  const params = new URLSearchParams({ rebuild: String(options.rebuild ?? false) });
  return getJson<CalendarOverlay>(`/calendar/overlay?${params.toString()}`);
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

export function getOperatorCockpit(): Promise<OperatorCockpit> {
  return getJson<OperatorCockpit>("/operator/cockpit");
}

export function getOpportunityWorkbench(): Promise<OpportunityWorkbench> {
  return getJson<OpportunityWorkbench>("/opportunities/workbench");
}

export function getResearchers(): Promise<Researcher[]> {
  return getJson<Researcher[]>("/researchers");
}

export function getInstitutions(): Promise<Institution[]> {
  return getJson<Institution[]>("/institutions");
}

export function getResearcher(id: string): Promise<ResearcherDetail> {
  return getJson<ResearcherDetail>(`/researchers/${id}`);
}

export function getSpeakerProfile(id: string): Promise<SpeakerProfile> {
  return getJson<SpeakerProfile>(`/speakers/${id}/profile`);
}

export async function updateSpeakerProfile(id: string, payload: Omit<SpeakerProfile, "id" | "researcher_id" | "created_at" | "updated_at">): Promise<SpeakerProfile> {
  return getJson<SpeakerProfile>(`/speakers/${id}/profile`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getInstitutionProfile(id: string): Promise<InstitutionProfile> {
  return getJson<InstitutionProfile>(`/institutions/${id}/profile`);
}

export async function updateInstitutionProfile(
  id: string,
  payload: Omit<InstitutionProfile, "id" | "institution_id" | "created_at" | "updated_at">,
): Promise<InstitutionProfile> {
  return getJson<InstitutionProfile>(`/institutions/${id}/profile`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getWishlist(): Promise<WishlistEntry[]> {
  return getJson<WishlistEntry[]>("/wishlist");
}

export function getWishlistAlerts(): Promise<WishlistAlert[]> {
  return getJson<WishlistAlert[]>("/wishlist-alerts");
}

export function getWishlistMatches(): Promise<WishlistMatchGroup[]> {
  return getJson<WishlistMatchGroup[]>("/wishlist-matches");
}

export async function refreshWishlistMatches(): Promise<WishlistMatchGroup[]> {
  return getJson<WishlistMatchGroup[]>("/wishlist-matches/refresh", {
    method: "POST",
  });
}

export async function updateWishlistMatchStatus(matchId: string, status: string, note?: string): Promise<WishlistMatchGroup> {
  return getJson<WishlistMatchGroup>(`/wishlist-matches/${matchId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, note: note ?? null }),
  });
}

export async function updateWishlistAlertStatus(alertId: string, status: string, note?: string): Promise<WishlistAlert> {
  return getJson<WishlistAlert>(`/wishlist-alerts/${alertId}`, {
    method: "PATCH",
    body: JSON.stringify({ status, note: note ?? null }),
  });
}

export async function createWishlistEntry(payload: {
  institution_id: string;
  researcher_id?: string | null;
  speaker_name?: string | null;
  topic?: string | null;
  priority: number;
  status: string;
  notes?: string | null;
  metadata_json?: Record<string, unknown>;
}): Promise<WishlistEntry> {
  return getJson<WishlistEntry>("/wishlist", {
    method: "POST",
    body: JSON.stringify({ ...payload, metadata_json: payload.metadata_json ?? {} }),
  });
}

export async function updateWishlistEntry(entryId: string, payload: {
  institution_id: string;
  researcher_id?: string | null;
  speaker_name?: string | null;
  topic?: string | null;
  priority: number;
  status: string;
  notes?: string | null;
  metadata_json?: Record<string, unknown>;
}): Promise<WishlistEntry> {
  return getJson<WishlistEntry>(`/wishlist/${entryId}`, {
    method: "PATCH",
    body: JSON.stringify({ ...payload, metadata_json: payload.metadata_json ?? {} }),
  });
}

export async function deleteWishlistEntry(entryId: string): Promise<void> {
  await getJson<void>(`/wishlist/${entryId}`, {
    method: "DELETE",
  });
}

export function getTourLegs(): Promise<TourLeg[]> {
  return getJson<TourLeg[]>("/tour-legs");
}

export function getTourLeg(id: string): Promise<TourLeg> {
  return getJson<TourLeg>(`/tour-legs/${id}`);
}

export function getTravelPriceChecks(tourLegId?: string): Promise<TravelPriceCheck[]> {
  const params = new URLSearchParams();
  if (tourLegId) {
    params.set("tour_leg_id", tourLegId);
  }
  const query = params.toString();
  return getJson<TravelPriceCheck[]>(query ? `/travel-price-checks?${query}` : "/travel-price-checks");
}

export async function createTravelPriceCheck(payload: {
  origin_city: string;
  destination_city: string;
  departure_at?: string | null;
  tour_leg_id?: string | null;
  force_refresh?: boolean;
  travel_class?: string;
  fare_policy?: string;
}): Promise<TravelPriceCheck> {
  return getJson<TravelPriceCheck>("/travel-price-checks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function refreshTourLegPrices(tourLegId: string): Promise<TourLeg> {
  return getJson<TourLeg>(`/tour-legs/${tourLegId}/refresh-prices`, {
    method: "POST",
  });
}

export async function proposeTourLeg(tripClusterId: string, feePerStopChf?: number | null): Promise<TourLeg> {
  const payload: Record<string, unknown> = { trip_cluster_id: tripClusterId };
  if (feePerStopChf !== undefined && feePerStopChf !== null) {
    payload.fee_per_stop_chf = feePerStopChf;
  }
  return getJson<TourLeg>("/tour-legs/propose", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getTourAssemblies(): Promise<TourAssemblyProposal[]> {
  return getJson<TourAssemblyProposal[]>("/tour-assemblies");
}

export function getTourAssembly(id: string): Promise<TourAssemblyProposal> {
  return getJson<TourAssemblyProposal>(`/tour-assemblies/${id}`);
}

export async function proposeTourAssembly(matchGroupId: string): Promise<TourAssemblyProposal> {
  return getJson<TourAssemblyProposal>("/tour-assemblies/propose", {
    method: "POST",
    body: JSON.stringify({ match_group_id: matchGroupId }),
  });
}

export async function createTourAssemblySpeakerDraft(proposalId: string): Promise<OutreachDraft> {
  return getJson<OutreachDraft>(`/tour-assemblies/${proposalId}/speaker-draft`, {
    method: "POST",
  });
}

export function getRelationshipBrief(speakerId: string, institutionId: string): Promise<RelationshipBrief> {
  return getJson<RelationshipBrief>(`/relationship-briefs/${speakerId}/${institutionId}`);
}

export async function updateRelationshipBrief(
  speakerId: string,
  institutionId: string,
  payload: Omit<RelationshipBrief, "id" | "researcher_id" | "institution_id" | "created_at" | "updated_at">,
): Promise<RelationshipBrief> {
  return getJson<RelationshipBrief>(`/relationship-briefs/${speakerId}/${institutionId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function createFeedbackSignal(payload: {
  researcher_id: string;
  institution_id: string;
  tour_leg_id?: string | null;
  party: string;
  signal_type: string;
  value: string;
  sentiment_score?: number | null;
  notes?: string | null;
  metadata_json?: Record<string, unknown>;
}): Promise<FeedbackSignal> {
  return getJson<FeedbackSignal>("/feedback-signals", {
    method: "POST",
    body: JSON.stringify({ ...payload, metadata_json: payload.metadata_json ?? {} }),
  });
}

export function getAuditEvents(): Promise<AuditEvent[]> {
  return getJson<AuditEvent[]>("/audit-events");
}

export function getBusinessCaseRuns(): Promise<BusinessCaseRun[]> {
  return getJson<BusinessCaseRun[]>("/business-cases/runs");
}

export function getBusinessCaseRun(id: string): Promise<BusinessCaseRun> {
  return getJson<BusinessCaseRun>(`/business-cases/runs/${id}`);
}

export async function runBusinessCaseAudit(): Promise<BusinessCaseRun> {
  return getJson<BusinessCaseRun>("/business-cases/run", {
    method: "POST",
  });
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

export async function createDraft(researcherId: string, tripClusterId: string, templateKey = "kof_invitation"): Promise<OutreachDraft> {
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

export async function runMorningSweep(): Promise<MorningSweepResponse> {
  return getJson<MorningSweepResponse>("/operator/morning-sweep", {
    method: "POST",
  });
}

export async function runRealSync(): Promise<MorningSweepResponse> {
  return getJson<MorningSweepResponse>("/operator/real-sync", {
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

export async function runEvidenceSearch(researcherId?: string): Promise<JobRunResponse> {
  const path = researcherId ? `/researchers/${researcherId}/evidence-search` : "/jobs/evidence-search";
  const body = researcherId ? undefined : JSON.stringify({ researcher_id: null });
  return getJson<JobRunResponse>(path, {
    method: "POST",
    body,
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
