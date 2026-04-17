import Link from "next/link";

import { Panel } from "@/components/panel";
import { ScoreBadge } from "@/components/score-badge";
import { getCalendarOverlay, getDailyCatch, getResearchers } from "@/lib/api";

export default async function HomePage() {
  const [dailyCatch, overlay, researchers] = await Promise.all([
    getDailyCatch(),
    getCalendarOverlay(),
    getResearchers(),
  ]);

  const topScore = dailyCatch.top_clusters[0]?.opportunity_score ?? 0;

  return (
    <>
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Logistical Oracle</span>
          <h1 className="hero-title">Where Europe&apos;s seminar trail meets Zurich precision.</h1>
          <p className="hero-copy">
            Academic Tour Guide listens to external seminar hubs, maps biographic hooks, and turns the KOF calendar into invitation-ready
            windows with a human-reviewed draft on the other side.
          </p>
          <div className="kpi-grid">
            <div className="metric">
              <div className="metric-value">{dailyCatch.recent_events.length}</div>
              <div className="metric-label">Recent names in the last 24h</div>
            </div>
            <div className="metric">
              <div className="metric-value">{overlay.open_windows.length}</div>
              <div className="metric-label">Open KOF windows</div>
            </div>
            <div className="metric">
              <div className="metric-value">{topScore}</div>
              <div className="metric-label">Top current opportunity score</div>
            </div>
          </div>
        </div>
        <Panel
          title="Pilot watchlist"
          copy="The v1 crawler is tuned to DACH-adjacent and policy-heavy sources."
        >
          <div className="timeline-strip">
            {["Bocconi", "Mannheim", "Bonn", "ECB", "BIS", "KOF Host Calendar"].map((label) => (
              <span className="timeline-chip" key={label}>
                {label}
              </span>
            ))}
          </div>
          <p className="fine-print">
            KOF public events are treated as occupied dates. Open invitation windows are derived from recurring templates and overrides.
          </p>
        </Panel>
      </section>

      <section className="content-grid">
        <Panel title="Trip clusters" copy="Ranked by Zurich-specific invitation fit.">
          <div className="card-list">
            {dailyCatch.top_clusters.map((cluster) => (
              <div className="list-card" key={cluster.id}>
                <div className="panel-header">
                  <div>
                    <h3>
                      {cluster.start_date} to {cluster.end_date}
                    </h3>
                    <p className="muted">{cluster.itinerary.map((stop) => stop.city).join(" -> ")}</p>
                  </div>
                  <ScoreBadge score={cluster.opportunity_score} />
                </div>
                <div className="timeline-strip">
                  {cluster.rationale.map((entry) => (
                    <span className="timeline-chip" key={`${cluster.id}-${entry.label}`}>
                      {entry.label} +{entry.points}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Daily Catch" copy="Newly scraped appearances from the pilot hub set.">
          <div className="event-list">
            {dailyCatch.recent_events.map((event) => (
              <div className="list-card" key={event.id}>
                <h3>{event.speaker_name}</h3>
                <p className="muted">
                  {event.title} | {event.city}, {event.country}
                </p>
                <p className="fine-print">
                  {new Date(event.starts_at).toLocaleString()} | {event.source_name.toUpperCase()}
                </p>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      <section className="dual-grid">
        <Panel title="KOF calendar overlay" copy="Host events block derived invitation windows.">
          <div className="card-list">
            {overlay.open_windows.map((window) => (
              <div className="list-card" key={window.id}>
                <div className="panel-header">
                  <h3>{new Date(window.starts_at).toLocaleString()}</h3>
                  <span className="status-pill">{window.source}</span>
                </div>
                <p className="muted">Until {new Date(window.ends_at).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Researcher ledger" copy="Evidence-backed profiles and itinerary context.">
          <div className="card-list">
            {researchers.map((researcher) => (
              <div className="list-card" key={researcher.id}>
                <div className="panel-header">
                  <div>
                    <h3>{researcher.name}</h3>
                    <p className="muted">{researcher.home_institution || "Institution pending"}</p>
                  </div>
                  <Link className="ghost-button" href={`/researchers/${researcher.id}`}>
                    View dossier
                  </Link>
                </div>
                <div className="timeline-strip">
                  {researcher.facts.map((fact) => (
                    <span className="timeline-chip" key={fact.id}>
                      {fact.fact_type}: {fact.value}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </section>
    </>
  );
}

