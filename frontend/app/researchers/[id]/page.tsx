import Link from "next/link";

import { ActionNotice } from "@/components/action-notice";
import { DraftButton } from "@/components/draft-button";
import { ManualFactForm } from "@/components/manual-fact-form";
import { Panel } from "@/components/panel";
import { ResearcherRefreshActions } from "@/components/researcher-refresh-actions";
import { ScoreBadge } from "@/components/score-badge";
import { TourLegButton } from "@/components/tour-leg-button";
import { getInstitutions, getRelationshipBrief, getResearcher, getSpeakerProfile } from "@/lib/api";

export const dynamic = "force-dynamic";

type ResearcherPageProps = {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ missing_fact?: string | string[] }>;
};

function missingFactsFromParam(value: string | string[] | undefined): string[] {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  return values
    .flatMap((item) => item.split(","))
    .map((item) => item.trim())
    .filter((item) => item === "phd_institution" || item === "nationality" || item === "home_institution" || item === "birth_month");
}

export default async function ResearcherPage({ params, searchParams }: ResearcherPageProps) {
  const { id } = await params;
  const query = searchParams ? await searchParams : {};
  const missingFacts = missingFactsFromParam(query.missing_fact);
  const [researcher, speakerProfile, institutions] = await Promise.all([getResearcher(id), getSpeakerProfile(id), getInstitutions()]);
  const kof = institutions.find((institution) => institution.name.includes("KOF")) ?? institutions[0];
  const relationshipBrief = kof ? await getRelationshipBrief(id, kof.id) : null;

  const approvedFacts = researcher.facts;
  const pendingFacts = researcher.fact_candidates.filter((candidate) => candidate.status === "pending");

  return (
    <div className="stack">
      <Panel
        title={researcher.name}
        copy={researcher.home_institution || "Home institution pending enrichment"}
        rightSlot={<Link className="ghost-button" href="/">Back to Start</Link>}
      >
        <div className="facts-grid">
          {approvedFacts.map((fact) => (
            <article className="fact-card" key={fact.id}>
              <strong>{fact.fact_type}</strong>
              <p>{fact.value}</p>
              <p className="fine-print">
                Approved via {fact.approval_origin} | Confidence {Math.round(fact.confidence * 100)}%
              </p>
              {fact.evidence_snippet ? <p className="fine-print">{fact.evidence_snippet}</p> : null}
            </article>
          ))}
        </div>
      </Panel>

      <section className="dual-grid">
        <Panel title="Roadshow speaker profile" copy="Touring preferences and rider notes used by Relations Manager.">
          <div className="card-list">
            <div className="list-card">
              <h3>Topics</h3>
              <p className="muted">{speakerProfile.topics.length ? speakerProfile.topics.join(", ") : "No topics captured yet"}</p>
            </div>
            <div className="list-card">
              <h3>Commercial and timing guardrails</h3>
              <p className="muted">
                Fee floor {speakerProfile.fee_floor_chf ? `CHF ${speakerProfile.fee_floor_chf}` : "pending"} | Notice{" "}
                {speakerProfile.notice_period_days ?? "pending"} days
              </p>
              <p className="fine-print">
                {speakerProfile.verification_status} | {speakerProfile.consent_status}
              </p>
            </div>
            <div className="list-card">
              <h3>Rider and travel</h3>
              <p className="fine-print">{JSON.stringify({ travel: speakerProfile.travel_preferences, rider: speakerProfile.rider })}</p>
            </div>
          </div>
        </Panel>

        <Panel title="KOF relationship memory" copy="Compact Relations Manager brief for this speaker-institution pair.">
          {relationshipBrief ? (
            <div className="card-list">
              <div className="list-card">
                <h3>Summary</h3>
                <p className="muted">{relationshipBrief.summary}</p>
              </div>
              <div className="list-card">
                <h3>Forward signals</h3>
                <p className="fine-print">{JSON.stringify(relationshipBrief.forward_signals)}</p>
              </div>
            </div>
          ) : (
            <p className="fine-print">No KOF institution profile is available yet.</p>
          )}
        </Panel>
      </section>

      <section className="dual-grid">
        <Panel title="Evidence search" copy="Search trusted public sources without leaving the dossier.">
          <div id="evidence-search" />
          <div className="card-list">
            <div className="list-card">
              <h3>Targeted pipeline controls</h3>
              <p className="muted">
                RePEc sync updates identity and ranking. Search trusted evidence checks RePEc Genealogy, ORCID, CEPR, institution-linked
                profiles, and CV links, then places extracted claims in the review queue.
              </p>
            </div>
            <ResearcherRefreshActions researcherId={researcher.id} />
          </div>
        </Panel>

        <div id="manual-facts">
          <Panel title="Manual approved facts" copy="Admin-entered facts are approved immediately and can unblock outreach drafts.">
            <ManualFactForm defaultHomeInstitution={researcher.home_institution} requiredFacts={missingFacts} researcherId={researcher.id} />
          </Panel>
        </div>
      </section>

      <section className="dual-grid">
        <Panel title="Pending evidence" copy="These candidate facts can influence scoring, but drafts stay blocked until reviewed.">
          <div className="card-list">
            {pendingFacts.length ? (
              pendingFacts.map((fact) => (
                <div className="list-card" key={fact.id}>
                  <h3>
                    {fact.fact_type}: {fact.value}
                  </h3>
                  <p className="fine-print">Confidence {Math.round(fact.confidence * 100)}% | {fact.origin}</p>
                  {fact.evidence_snippet ? <p className="fine-print">{fact.evidence_snippet}</p> : null}
                  <ActionNotice
                    severity="warning"
                    title="Evidence candidate needs approval"
                    explanation="Approve or reject this fact before Roadshow can use it in an outreach draft."
                    primaryAction={{
                      label: "Approve evidence for outreach",
                      consequence: "Opens the review queue filtered to this speaker and fact type.",
                      href: `/review?status=pending&researcher_id=${researcher.id}&fact_type=${fact.fact_type}`,
                    }}
                  />
                </div>
              ))
            ) : (
              <p className="fine-print">No pending fact candidates are currently waiting for review.</p>
            )}
          </div>
        </Panel>

        <Panel title="Source documents" copy="Institution-linked public pages and profiles used by the evidence agent.">
          <div className="card-list">
            {researcher.documents.length ? (
              researcher.documents.map((document) => (
                <div className="list-card" key={document.id}>
                  <h3>{document.title || document.url}</h3>
                  <p className="muted">{document.fetch_status.toUpperCase()} | {document.content_type || "unknown type"}</p>
                  {document.discovered_from_url ? <p className="fine-print">Discovered from {document.discovered_from_url}</p> : null}
                </div>
              ))
            ) : (
              <ActionNotice
                severity="info"
                title="No source documents fetched yet"
                explanation="Run trusted evidence search to fetch institution-linked profiles, CV links, ORCID, CEPR, and RePEc Genealogy pages."
                primaryAction={{
                  label: "Search trusted evidence",
                  consequence: "Jumps to the dossier controls that fetch sources and create review candidates.",
                  href: "#evidence-search",
                }}
              />
            )}
          </div>
        </Panel>
      </section>

      <section className="dual-grid">
        <Panel title="Opportunity windows" copy="Trip clusters and score rationale.">
          <div className="card-list">
            {researcher.trip_clusters.map((cluster) => (
              <div className="list-card" key={cluster.id}>
                <div className="panel-header">
                  <div>
                    <h3>
                      {cluster.start_date} to {cluster.end_date}
                    </h3>
                    <p className="muted">{cluster.itinerary.map((stop) => `${stop.city} (${stop.source_name})`).join(" -> ")}</p>
                  </div>
                  <ScoreBadge score={cluster.opportunity_score} />
                </div>
                {cluster.uses_unreviewed_evidence ? (
                  <ActionNotice
                    severity="warning"
                    title="Score uses unreviewed evidence"
                    explanation="This opportunity can be ranked, but outreach should wait until the evidence candidate is approved or rejected."
                    primaryAction={{
                      label: "Approve evidence for outreach",
                      consequence: "Opens the review queue filtered to this speaker.",
                      href: `/review?status=pending&researcher_id=${researcher.id}`,
                    }}
                    secondaryActions={[
                      {
                        label: "Search trusted evidence",
                        consequence: "Jumps to the dossier controls that can find stronger source documents.",
                        href: "#evidence-search",
                      },
                    ]}
                  />
                ) : null}
                <div className="timeline-strip">
                  {cluster.rationale.map((reason) => (
                    <span className="timeline-chip" key={`${cluster.id}-${reason.label}`}>
                      {reason.label}: {reason.detail}
                    </span>
                  ))}
                </div>
                <div className="template-actions">
                  <DraftButton researcherId={researcher.id} clusterId={cluster.id} />
                  <TourLegButton clusterId={cluster.id} />
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Observed appearances" copy="Raw seminar events feeding the current clusters.">
          <div className="event-list">
            {researcher.talk_events.map((event) => (
              <div className="list-card" key={event.id}>
                <h3>{event.title}</h3>
                <p className="muted">
                  {event.city}, {event.country} | {event.source_name.toUpperCase()}
                </p>
                <p className="fine-print">{new Date(event.starts_at).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      <Panel title="Identity ledger" copy="External researcher identities and rankings currently attached to this dossier.">
        <div className="card-list">
          {researcher.identities.length ? (
            researcher.identities.map((identity) => (
              <div className="list-card" key={identity.id}>
                <h3>{identity.provider.toUpperCase()}</h3>
                <p className="muted">{identity.canonical_name}</p>
                <p className="fine-print">
                  Match {Math.round(identity.match_confidence * 100)}%
                  {identity.ranking_percentile ? ` | Rank percentile ${identity.ranking_percentile}` : ""}
                </p>
              </div>
            ))
          ) : (
            <p className="fine-print">No external identities have been synced yet.</p>
          )}
        </div>
      </Panel>
    </div>
  );
}
