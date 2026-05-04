import { cookies } from "next/headers";

import {
  getJson,
  type BusinessCaseRun,
  type CalendarOverlay,
  type HostCalendarEvent,
  type Institution,
  type Me,
  type OpenSeminarWindow,
  type OperatorCockpit,
  type OperatorRunbook,
  type OpportunityCard,
  type OpportunityWorkbench,
  type OutreachDraft,
  type OutreachDraftListItem,
  type RelationshipBrief,
  type Researcher,
  type ResearcherDetail,
  type ReviewFact,
  type ReviewQueueFilters,
  type SeminarSlotOverride,
  type SeminarSlotTemplate,
  type SourceHealth,
  type SourceHealthRecord,
  type SourceReliability,
  type SpeakerProfile,
  type Tenant,
  type TenantSettings,
  type TenantSourceSubscription,
  type TourAssemblyProposal,
  type TourLeg,
  type WishlistAlert,
  type WishlistEntry,
  type WishlistMatchGroup,
} from "@/lib/api";

export { RoadshowApiError } from "@/lib/api";

export type {
  AuditEvent,
  BusinessCaseResult,
  BusinessCaseRun,
  CalendarOverlay,
  HostCalendarEvent,
  Institution,
  Me,
  OpenSeminarWindow,
  OperatorPrimaryFlow,
  OperatorRunbook,
  OperatorSetupBlocker,
  OpportunityCard,
  OpportunityWorkbench,
  OutreachDraft,
  OutreachDraftListItem,
  RelationshipBrief,
  Researcher,
  ResearcherDetail,
  ReviewFact,
  ReviewQueueFilters,
  RunbookStep,
  SeminarSlotOverride,
  SeminarSlotTemplate,
  SourceHealth,
  SourceHealthRecord,
  SourceReliability,
  SpeakerProfile,
  Tenant,
  TenantSettings,
  TenantSourceSubscription,
  TourAssemblyProposal,
  TourLeg,
  WishlistAlert,
  WishlistEntry,
  WishlistMatchGroup,
} from "@/lib/api";

async function serverJson<T>(path: string, init?: RequestInit): Promise<T> {
  const cookieHeader = (await cookies()).toString();
  const headers = new Headers(init?.headers);
  if (cookieHeader && !headers.has("Cookie")) {
    headers.set("Cookie", cookieHeader);
  }
  return getJson<T>(path, { ...init, headers });
}

export function getBusinessCaseRuns(): Promise<BusinessCaseRun[]> {
  return serverJson<BusinessCaseRun[]>("/business-cases/runs");
}

export function getCalendarOverlay(options: { rebuild?: boolean } = {}): Promise<CalendarOverlay> {
  const params = new URLSearchParams({ rebuild: String(options.rebuild ?? false) });
  return serverJson<CalendarOverlay>(`/calendar/overlay?${params.toString()}`);
}

export function getCurrentTenant(): Promise<Tenant> {
  return serverJson<Tenant>("/tenants/current");
}

export function getCurrentTenantSettings(): Promise<TenantSettings> {
  return serverJson<TenantSettings>("/tenants/current/settings");
}

export function getDraft(id: string): Promise<OutreachDraft> {
  return serverJson<OutreachDraft>(`/outreach-drafts/${id}`);
}

export function getDrafts(status?: string): Promise<OutreachDraftListItem[]> {
  return serverJson<OutreachDraftListItem[]>(
    status ? `/outreach-drafts?status=${encodeURIComponent(status)}` : "/outreach-drafts",
  );
}

export function getInstitutions(): Promise<Institution[]> {
  return serverJson<Institution[]>("/institutions");
}

export function getMe(): Promise<Me> {
  return serverJson<Me>("/me");
}

export function getOperatorCockpit(): Promise<OperatorCockpit> {
  return serverJson<OperatorCockpit>("/operator/cockpit");
}

export function getOperatorRunbook(): Promise<OperatorRunbook> {
  return serverJson<OperatorRunbook>("/operator/runbook");
}

export function getOpportunityWorkbench(): Promise<OpportunityWorkbench> {
  return serverJson<OpportunityWorkbench>("/opportunities/workbench");
}

export function getRelationshipBrief(speakerId: string, institutionId: string): Promise<RelationshipBrief> {
  return serverJson<RelationshipBrief>(`/relationship-briefs/${speakerId}/${institutionId}`);
}

export function getResearcher(id: string): Promise<ResearcherDetail> {
  return serverJson<ResearcherDetail>(`/researchers/${id}`);
}

export function getResearchers(): Promise<Researcher[]> {
  return serverJson<Researcher[]>("/researchers");
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
  return serverJson<ReviewFact[]>(`/review/facts?${params.toString()}`);
}

export function getSeminarOverrides(): Promise<SeminarSlotOverride[]> {
  return serverJson<SeminarSlotOverride[]>("/seminar/overrides");
}

export function getSeminarTemplates(): Promise<SeminarSlotTemplate[]> {
  return serverJson<SeminarSlotTemplate[]>("/seminar/templates");
}

export function getSourceHealth(): Promise<SourceHealth[]> {
  return serverJson<SourceHealth[]>("/source-health");
}

export function getSourceHealthHistory(): Promise<SourceHealthRecord[]> {
  return serverJson<SourceHealthRecord[]>("/source-health/history");
}

export function getSourceReliability(): Promise<SourceReliability[]> {
  return serverJson<SourceReliability[]>("/source-health/reliability");
}

export function getSpeakerProfile(id: string): Promise<SpeakerProfile> {
  return serverJson<SpeakerProfile>(`/speakers/${id}/profile`);
}

export function getTenantSourceSubscriptions(): Promise<TenantSourceSubscription[]> {
  return serverJson<TenantSourceSubscription[]>("/tenant/source-subscriptions");
}

export function getTourAssemblies(): Promise<TourAssemblyProposal[]> {
  return serverJson<TourAssemblyProposal[]>("/tour-assemblies");
}

export function getTourAssembly(id: string): Promise<TourAssemblyProposal> {
  return serverJson<TourAssemblyProposal>(`/tour-assemblies/${id}`);
}

export function getTourLeg(id: string): Promise<TourLeg> {
  return serverJson<TourLeg>(`/tour-legs/${id}`);
}

export function getTourLegs(): Promise<TourLeg[]> {
  return serverJson<TourLeg[]>("/tour-legs");
}

export function getWishlist(): Promise<WishlistEntry[]> {
  return serverJson<WishlistEntry[]>("/wishlist");
}

export function getWishlistAlerts(): Promise<WishlistAlert[]> {
  return serverJson<WishlistAlert[]>("/wishlist-alerts");
}

export function getWishlistMatches(): Promise<WishlistMatchGroup[]> {
  return serverJson<WishlistMatchGroup[]>("/wishlist-matches");
}
