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

export type CalendarOverlay = {
  host_events: HostCalendarEvent[];
  open_windows: OpenSeminarWindow[];
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
  created_at: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
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
  return (await response.json()) as T;
}

export function getDailyCatch(): Promise<DailyCatch> {
  return getJson<DailyCatch>("/dashboard/daily-catch");
}

export function getCalendarOverlay(): Promise<CalendarOverlay> {
  return getJson<CalendarOverlay>("/calendar/overlay?rebuild=true");
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

export function getReviewQueue(): Promise<ReviewFact[]> {
  return getJson<ReviewFact[]>("/review/facts?status=pending");
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

export async function createDraft(researcherId: string, tripClusterId: string): Promise<OutreachDraft> {
  return getJson<OutreachDraft>("/outreach-drafts", {
    method: "POST",
    body: JSON.stringify({ researcher_id: researcherId, trip_cluster_id: tripClusterId }),
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
