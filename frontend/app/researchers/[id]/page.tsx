import Link from "next/link";

import { DraftButton } from "@/components/draft-button";
import { ManualFactForm } from "@/components/manual-fact-form";
import { Panel } from "@/components/panel";
import { ScoreBadge } from "@/components/score-badge";
import { getResearcher } from "@/lib/api";

type ResearcherPageProps = {
  params: Promise<{ id: string }>;
};

export default async function ResearcherPage({ params }: ResearcherPageProps) {
  const { id } = await params;
  const researcher = await getResearcher(id);

  const approvedFacts = researcher.facts;
  const pendingFacts = researcher.fact_candidates.filter((candidate) => candidate.status === "pending");

  return (
    <div className="stack">
      <Panel
        title={researcher.name}
        copy={researcher.home_institution || "Home institution pending enrichment"}
        rightSlot={<Link className="ghost-button" href="/">Back to dashboard</Link>}
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
        <Panel title="Manual approved facts" copy="Admin-entered facts are approved immediately and can unblock outreach drafts.">
          <ManualFactForm defaultHomeInstitution={researcher.home_institution} researcherId={researcher.id} />
        </Panel>

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
                </div>
              ))
            ) : (
              <p className="fine-print">No pending fact candidates are currently waiting for review.</p>
            )}
          </div>
        </Panel>
      </section>

      <Panel title="Source documents" copy="Institution-linked public pages and profiles used by the biographer pipeline.">
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
            <p className="fine-print">No linked source documents have been fetched for this dossier yet.</p>
          )}
        </div>
      </Panel>

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
                {cluster.uses_unreviewed_evidence ? <p className="fine-print">This score currently relies on at least one unreviewed fact candidate.</p> : null}
                <div className="timeline-strip">
                  {cluster.rationale.map((reason) => (
                    <span className="timeline-chip" key={`${cluster.id}-${reason.label}`}>
                      {reason.label}: {reason.detail}
                    </span>
                  ))}
                </div>
                <DraftButton researcherId={researcher.id} clusterId={cluster.id} />
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
