import Link from "next/link";

import { FeedbackSignalForm } from "@/components/feedback-signal-form";
import { Panel } from "@/components/panel";
import { getInstitutions, getTourLeg } from "@/lib/api";

type TourLegPageProps = {
  params: Promise<{ id: string }>;
};

function asMoney(value: number): string {
  return `CHF ${value.toLocaleString()}`;
}

export default async function TourLegPage({ params }: TourLegPageProps) {
  const { id } = await params;
  const [tourLeg, institutions] = await Promise.all([getTourLeg(id), getInstitutions()]);
  const kof = institutions.find((institution) => institution.name.includes("KOF")) ?? institutions[0];

  return (
    <div className="stack">
      <Panel
        title={tourLeg.title}
        copy={`${tourLeg.start_date} to ${tourLeg.end_date} | ${tourLeg.status}`}
        rightSlot={<Link className="ghost-button" href="/tour-legs">Back to tour legs</Link>}
      >
        <div className="kpi-grid">
          <div className="metric">
            <div className="metric-value">{tourLeg.stops.length}</div>
            <div className="metric-label">Modeled stops</div>
          </div>
          <div className="metric">
            <div className="metric-value">{asMoney(tourLeg.estimated_fee_total_chf)}</div>
            <div className="metric-label">Speaker fees</div>
          </div>
          <div className="metric">
            <div className="metric-value">{asMoney(tourLeg.estimated_travel_total_chf)}</div>
            <div className="metric-label">Travel pool</div>
          </div>
        </div>
      </Panel>

      <section className="dual-grid">
        <Panel title="Stops" copy="Known external appearances plus the candidate KOF stop.">
          <div className="card-list">
            {tourLeg.stops.map((stop) => (
              <div className="list-card" key={stop.id}>
                <div className="panel-header">
                  <div>
                    <h3>
                      {stop.sequence}. {stop.city}
                    </h3>
                    <p className="muted">
                      {stop.format} | {stop.starts_at ? new Date(stop.starts_at).toLocaleString() : "Date pending"}
                    </p>
                  </div>
                  <span className="status-pill">{stop.status}</span>
                </div>
                <div className="timeline-strip">
                  <span className="timeline-chip">Fee {asMoney(stop.fee_chf)}</span>
                  <span className="timeline-chip">Travel share {asMoney(stop.travel_share_chf)}</span>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Cost split" copy="Pure deterministic calculation; no live booking or invoice has been triggered.">
          <div className="card-list">
            {Object.entries(tourLeg.cost_split_json).map(([key, value]) => (
              <div className="list-card" key={key}>
                <h3>{key.replaceAll("_", " ")}</h3>
                <p className="fine-print">{Array.isArray(value) ? value.join(" ") : String(value)}</p>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      <section className="dual-grid">
        <Panel title="Rationale" copy="Why Negotiator-lite produced this proposal.">
          <div className="card-list">
            {tourLeg.rationale.map((item, index) => (
              <div className="list-card" key={`${index}-${String(item.label)}`}>
                <h3>{String(item.label ?? "Rationale")}</h3>
                <p className="fine-print">{String(item.detail ?? "")}</p>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Feedback capture" copy="Manual post-event or admin signals update Roadshow relationship memory.">
          {kof ? <FeedbackSignalForm institutionId={kof.id} researcherId={tourLeg.researcher_id} tourLegId={tourLeg.id} /> : null}
        </Panel>
      </section>
    </div>
  );
}
