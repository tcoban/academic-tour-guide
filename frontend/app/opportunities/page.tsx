import Link from "next/link";

import { DraftButton } from "@/components/draft-button";
import { Panel } from "@/components/panel";
import { ScoreBadge } from "@/components/score-badge";
import { getOpportunityWorkbench } from "@/lib/api";

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString();
}

function fitCopy(fitType: string, distanceDays: number): string {
  if (fitType === "overlap") {
    return "Overlaps trip";
  }
  if (fitType === "nearby") {
    return `${distanceDays} days from trip`;
  }
  return `${fitType.replace("_", " ")} by ${distanceDays} days`;
}

function recommendationTone(recommendation: string): string {
  if (recommendation === "strong") {
    return "";
  }
  if (recommendation === "moderate") {
    return "warning";
  }
  return "blocked";
}

export default async function OpportunitiesPage() {
  const workbench = await getOpportunityWorkbench();
  const draftReady = workbench.opportunities.filter((item) => item.draft_ready).length;
  const matched = workbench.opportunities.filter((item) => item.best_window?.within_scoring_window).length;
  const topScore = workbench.opportunities[0]?.cluster.opportunity_score ?? 0;

  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Opportunity Workbench</span>
          <h1 className="hero-title">Turn trip clusters into invite decisions.</h1>
          <p className="hero-copy">
            Each card combines the researcher&apos;s European window, the best currently open KOF slot, draft readiness, and the score rationale
            that got it onto the shortlist.
          </p>
          <div className="kpi-grid">
            <div className="metric">
              <div className="metric-value">{workbench.opportunities.length}</div>
              <div className="metric-label">Ranked opportunities</div>
            </div>
            <div className="metric">
              <div className="metric-value">{matched}</div>
              <div className="metric-label">With scoring-window slot fit</div>
            </div>
            <div className="metric">
              <div className="metric-value">{draftReady}</div>
              <div className="metric-label">Draft-ready dossiers</div>
            </div>
          </div>
        </div>
        <Panel title="Calendar pressure" copy="Occupied KOF events and open windows currently in the workbench.">
          <div className="card-list">
            <div className="list-card">
              <h3>{workbench.open_windows.length} open windows</h3>
              <p className="muted">Derived from seminar templates minus host events and manual blocks.</p>
            </div>
            <div className="list-card">
              <h3>{workbench.host_events.length} occupied KOF events</h3>
              <p className="muted">Scraped from the KOF/ETH public calendar feed.</p>
            </div>
            <div className="list-card">
              <h3>{topScore} top score</h3>
              <p className="muted">The highest currently ranked Zurich opportunity.</p>
            </div>
          </div>
        </Panel>
      </section>

      <section className="opportunity-grid">
        {workbench.opportunities.map((item) => (
          <article className="opportunity-card" key={item.cluster.id}>
            <div className="panel-header">
              <div>
                <span className="eyebrow">{item.cluster.start_date} to {item.cluster.end_date}</span>
                <h2>{item.researcher.name}</h2>
                <p className="muted">{item.researcher.home_institution || "Institution pending"}</p>
              </div>
              <ScoreBadge score={item.cluster.opportunity_score} />
            </div>

            <div className="opportunity-section">
              <h3>European trail</h3>
              <div className="timeline-strip">
                {item.cluster.itinerary.map((stop) => (
                  <span className="timeline-chip" key={`${item.cluster.id}-${stop.starts_at}-${stop.city}`}>
                    {stop.city} · {new Date(stop.starts_at).toLocaleDateString()}
                  </span>
                ))}
              </div>
            </div>

            <div className="opportunity-section">
              <h3>Best KOF slot</h3>
              {item.best_window ? (
                <div className="slot-card">
                  <div>
                    <strong>{formatDateTime(item.best_window.starts_at)}</strong>
                    <p className="muted">Until {formatDateTime(item.best_window.ends_at)}</p>
                  </div>
                  <span className={`status-pill ${item.best_window.within_scoring_window ? "" : "warning"}`}>
                    {fitCopy(item.best_window.fit_type, item.best_window.distance_days)}
                  </span>
                </div>
              ) : (
                <p className="fine-print">No open KOF slot is currently available.</p>
              )}
            </div>

            <div className="opportunity-section">
              <h3>Cost-sharing calculator</h3>
              {item.cost_share ? (
                <div className="slot-card">
                  <div>
                    <strong>
                      CHF {item.cost_share.multi_city_incremental_chf} add-on vs CHF {item.cost_share.baseline_round_trip_chf} standalone
                    </strong>
                    <p className="muted">
                      Nearest stop: {item.cost_share.nearest_itinerary_city} ({item.cost_share.nearest_distance_km} km,{" "}
                      {item.cost_share.recommended_mode})
                    </p>
                    <p className="fine-print">
                      Estimated savings CHF {item.cost_share.estimated_savings_chf} | ROI {item.cost_share.roi_percent}%
                    </p>
                  </div>
                  <span className={`status-pill ${recommendationTone(item.cost_share.recommendation)}`}>
                    {item.cost_share.recommendation}
                  </span>
                </div>
              ) : (
                <p className="fine-print">No cost-sharing estimate is available without a recognized itinerary city.</p>
              )}
            </div>

            <div className="opportunity-section">
              <h3>Why it ranks</h3>
              <div className="timeline-strip">
                {item.draft_count > 0 ? (
                  <span className="timeline-chip">
                    {item.draft_count} draft{item.draft_count === 1 ? "" : "s"}
                  </span>
                ) : null}
                {item.cluster.rationale.map((entry) => (
                  <span className="timeline-chip" key={`${item.cluster.id}-${entry.label}`}>
                    {entry.label} +{entry.points}
                  </span>
                ))}
              </div>
              {item.cluster.uses_unreviewed_evidence ? (
                <p className="fine-print">One or more score signals still need human evidence review.</p>
              ) : null}
            </div>

            <div className="opportunity-actions">
              <Link className="ghost-button" href={`/researchers/${item.researcher.id}`}>
                View dossier
              </Link>
              {item.latest_draft_id ? (
                <Link className="ghost-button" href={`/drafts/${item.latest_draft_id}`}>
                  Latest draft
                </Link>
              ) : null}
              {item.draft_ready ? (
                <div className="template-actions">
                  <DraftButton researcherId={item.researcher.id} clusterId={item.cluster.id} label="Concierge" templateKey="concierge" />
                  <DraftButton
                    className="ghost-button"
                    researcherId={item.researcher.id}
                    clusterId={item.cluster.id}
                    label="Academic hook"
                    templateKey="academic_home"
                  />
                  <DraftButton
                    className="ghost-button"
                    researcherId={item.researcher.id}
                    clusterId={item.cluster.id}
                    label="Cost-share"
                    templateKey="cost_share"
                  />
                </div>
              ) : (
                <div className="draft-blocker">
                  <strong>Draft blocked</strong>
                  {item.draft_blockers.map((blocker) => (
                    <span key={`${item.cluster.id}-${blocker}`}>{blocker}</span>
                  ))}
                </div>
              )}
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
