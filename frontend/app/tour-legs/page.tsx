import Link from "next/link";

import { Panel } from "@/components/panel";
import { getTourLegs } from "@/lib/api";

function asMoney(value: number): string {
  return `CHF ${value.toLocaleString()}`;
}

export default async function TourLegsPage() {
  const tourLegs = await getTourLegs();
  const proposed = tourLegs.filter((leg) => leg.status === "proposed").length;
  const totalTravel = tourLegs.reduce((sum, leg) => sum + leg.estimated_travel_total_chf, 0);

  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Negotiator-lite</span>
          <h1 className="hero-title">Model KOF stops as Roadshow legs.</h1>
          <p className="hero-copy">
            Tour legs sit above trip clusters: ordered stops, candidate KOF slot, deterministic cost split, and reviewable assumptions.
          </p>
          <div className="kpi-grid">
            <div className="metric">
              <div className="metric-value">{tourLegs.length}</div>
              <div className="metric-label">Modeled legs</div>
            </div>
            <div className="metric">
              <div className="metric-value">{proposed}</div>
              <div className="metric-label">Proposed</div>
            </div>
            <div className="metric">
              <div className="metric-value">{asMoney(totalTravel)}</div>
              <div className="metric-label">Modeled travel pool</div>
            </div>
          </div>
        </div>
        <Panel title="How to create one" copy="Open Opportunities and click Propose tour leg on a shortlisted cluster.">
          <Link className="ghost-button" href="/opportunities">
            Open opportunities
          </Link>
        </Panel>
      </section>

      <Panel title="Tour-leg ledger" copy="Deterministic proposals only; no contracts, payment, or travel booking are executed here.">
        <div className="card-list">
          {tourLegs.length ? (
            tourLegs.map((leg) => (
              <div className="list-card" key={leg.id}>
                <div className="panel-header">
                  <div>
                    <h3>{leg.title}</h3>
                    <p className="muted">
                      {leg.start_date} to {leg.end_date} | {leg.stops.length} stops
                    </p>
                  </div>
                  <span className="status-pill">{leg.status}</span>
                </div>
                <div className="timeline-strip">
                  <span className="timeline-chip">Fees {asMoney(leg.estimated_fee_total_chf)}</span>
                  <span className="timeline-chip">Travel {asMoney(leg.estimated_travel_total_chf)}</span>
                  <span className="timeline-chip">
                    Share {asMoney(Number(leg.cost_split_json.per_stop_travel_share_chf ?? 0))}
                  </span>
                </div>
                <div className="template-actions">
                  <Link className="ghost-button" href={`/tour-legs/${leg.id}`}>
                    Open leg
                  </Link>
                </div>
              </div>
            ))
          ) : (
            <p className="fine-print">No Roadshow tour legs have been proposed yet.</p>
          )}
        </div>
      </Panel>
    </div>
  );
}
