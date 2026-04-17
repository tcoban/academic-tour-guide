import Link from "next/link";

import { DraftButton } from "@/components/draft-button";
import { Panel } from "@/components/panel";
import { ScoreBadge } from "@/components/score-badge";
import { getResearcher } from "@/lib/api";

type ResearcherPageProps = {
  params: Promise<{ id: string }>;
};

export default async function ResearcherPage({ params }: ResearcherPageProps) {
  const { id } = await params;
  const researcher = await getResearcher(id);

  return (
    <div className="stack">
      <Panel
        title={researcher.name}
        copy={researcher.home_institution || "Home institution pending enrichment"}
        rightSlot={<Link className="ghost-button" href="/">Back to dashboard</Link>}
      >
        <div className="facts-grid">
          {researcher.facts.map((fact) => (
            <article className="fact-card" key={fact.id}>
              <strong>{fact.fact_type}</strong>
              <p>{fact.value}</p>
              <p className="fine-print">Confidence {Math.round(fact.confidence * 100)}%</p>
              {fact.evidence_snippet ? <p className="fine-print">{fact.evidence_snippet}</p> : null}
            </article>
          ))}
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
    </div>
  );
}

