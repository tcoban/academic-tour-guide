import Link from "next/link";

import { ActionNotice } from "@/components/action-notice";
import { AiResearchFitButton } from "@/components/ai-research-fit-button";
import { AutopilotActionButton } from "@/components/autopilot-action-button";
import { DraftButton } from "@/components/draft-button";
import { Panel } from "@/components/panel";
import { ScoreBadge } from "@/components/score-badge";
import { TourLegButton } from "@/components/tour-leg-button";
import { getOpportunityWorkbench } from "@/lib/server-api";

export const dynamic = "force-dynamic";

type DraftBlockerAction = {
  message: string;
  action_label: string;
  action_href: string;
};

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

function travelTone(severity: string): string {
  if (severity === "strong" || severity === "good") {
    return "";
  }
  if (severity === "review") {
    return "warning";
  }
  return "blocked";
}

function autonomyTone(level: string): string {
  if (level === "autopilot_ready") {
    return "";
  }
  if (level === "assisted_autopilot" || level === "ai_research_needed") {
    return "warning";
  }
  return "blocked";
}

function blockerActions(item: { researcher: { id: string }; draft_blockers: string[]; draft_blocker_details?: DraftBlockerAction[] }): DraftBlockerAction[] {
  if (item.draft_blocker_details?.length) {
    return item.draft_blocker_details;
  }
  return item.draft_blockers.map((message) => ({
    message,
    action_label: "Edit speaker evidence",
    action_href: `/researchers/${item.researcher.id}#manual-facts`,
  }));
}

function routeLabel(item: {
  route_review_resolved: boolean;
  best_window?: { travel_fit_label?: string | null } | null;
}): string {
  if (item.route_review_resolved) {
    return "Route reviewed";
  }
  return item.best_window?.travel_fit_label || "Route review";
}

function firstDraftBlocker(item: {
  researcher: { id: string };
  draft_blockers: string[];
  draft_blocker_details?: DraftBlockerAction[];
}): DraftBlockerAction {
  return blockerActions(item)[0] ?? {
    message: "Approved evidence is required before Roadshow can create an invitation.",
    action_label: "Approve evidence for outreach",
    action_href: `/review?status=pending&researcher_id=${item.researcher.id}`,
  };
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
          <span className="eyebrow">Roadshow Workbench</span>
          <h1 className="hero-title">Turn Scout clusters into invite decisions.</h1>
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
        {workbench.opportunities.length === 0 ? (
          <div className="empty-state">
            <h3>No speaker opportunities yet.</h3>
            <p className="muted">
              Run real source sync from Start so Roadshow can show ranked seminar opportunities from watched institutions.
            </p>
            <Link className="button-link" href="/">
              Return to Start
            </Link>
          </div>
        ) : null}
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
                    {stop.city} | {new Date(stop.starts_at).toLocaleDateString()}
                  </span>
                ))}
              </div>
            </div>

            <div className="opportunity-section">
              <h3>Best KOF slot</h3>
              {item.best_window ? (
                <div className="stack">
                  <div className="slot-card">
                    <div>
                      <strong>{formatDateTime(item.best_window.starts_at)}</strong>
                      <p className="muted">Until {formatDateTime(item.best_window.ends_at)}</p>
                      {item.best_window.travel_fit_summary ? (
                        <p className="fine-print">{item.best_window.travel_fit_summary}</p>
                      ) : null}
                      {item.route_review_resolved ? <p className="fine-print">Route review exists for this opportunity.</p> : null}
                    </div>
                    <div className="pill-stack">
                      <span className="status-pill">
                        {fitCopy(item.best_window.fit_type, item.best_window.distance_days)}
                      </span>
                      <span
                        className={`status-pill ${
                          item.route_review_resolved ? "" : travelTone(item.best_window.travel_fit_severity)
                        }`}
                      >
                        {routeLabel(item)}
                      </span>
                    </div>
                  </div>
                  {item.route_review_action ? (
                    <ActionNotice
                      severity={item.route_review_resolved ? "info" : "warning"}
                      title={item.route_review_resolved ? "Route review is available" : "Route review advised"}
                      explanation={item.route_review_action.explanation}
                      primaryAction={{
                        label: item.route_review_action.label,
                        consequence: item.route_review_resolved
                          ? "Opens the existing route review so you can inspect ordering, rest days, and Zurich insertion."
                          : "Builds the KOF stop, route order, and internal cost review for this opportunity.",
                        href: item.route_review_action.href,
                        disabledReason: item.route_review_action.disabled_reason,
                      }}
                      primaryActionSlot={
                        item.route_review_action.href ? undefined : (
                          <TourLegButton
                            clusterId={item.cluster.id}
                            className="ghost-button"
                            label={item.route_review_action.label}
                          />
                        )
                      }
                    />
                  ) : null}
                </div>
              ) : (
                <ActionNotice
                  severity="blocked"
                  title="No open KOF slot is available"
                  explanation="Roadshow cannot rank or draft a concrete invitation until KOF has an open seminar window."
                  primaryAction={{
                    label: "Set weekly KOF slot",
                    consequence: "Opens KOF slot settings so you can define or reopen seminar capacity.",
                    href: "/seminar-admin",
                  }}
                  secondaryActions={[
                    {
                      label: "Inspect calendar overlay",
                      consequence: "Shows occupied KOF events and derived open windows.",
                      href: "/calendar",
                    },
                  ]}
                />
              )}
            </div>

            <div className="opportunity-section">
              <h3>Autopilot readiness</h3>
              {item.automation_assessment ? (
                <div className="slot-card">
                  <div>
                    <strong>{item.automation_assessment.score}% automation confidence</strong>
                    <p className="muted">{item.automation_assessment.summary}</p>
                    <p className="fine-print">
                      Next automated step: {item.automation_assessment.next_action.consequence}
                    </p>
                    <div className="timeline-strip">
                      {item.automation_assessment.signals.slice(0, 4).map((signal) => (
                        <span className="timeline-chip" key={`${item.cluster.id}-${signal.label}`} title={signal.detail}>
                          {signal.label}: {signal.confidence}%
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="pill-stack">
                    <span className={`status-pill ${autonomyTone(item.automation_assessment.level)}`}>
                      {item.automation_assessment.level.replaceAll("_", " ")}
                    </span>
                    <AutopilotActionButton
                      action={item.automation_assessment.next_action}
                      className="ghost-button"
                      clusterId={item.cluster.id}
                      draftReady={item.draft_ready}
                      latestTourLegId={item.latest_tour_leg_id}
                      researcherId={item.researcher.id}
                    />
                  </div>
                </div>
              ) : (
                <p className="fine-print">Automation assessment is not available for this opportunity yet.</p>
              )}
            </div>

            <div className="opportunity-section">
              <h3>Cost-sharing calculator</h3>
              {item.cost_share ? (
                <div className="stack">
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
                  {recommendationTone(item.cost_share.recommendation) ? (
                    <ActionNotice
                      severity="warning"
                      title="Cost review needs route context"
                      explanation="The estimate is useful for internal planning, but a modeled route is safer before invitation work."
                      primaryAction={{
                        label: item.latest_tour_leg_id ? "Open route and cost review" : "Build route and cost review",
                        consequence: item.latest_tour_leg_id
                          ? "Opens the modeled tour leg with first-class fare checks and Zurich hospitality."
                          : "Creates a modeled KOF stop with route order, first-class fare checks, and Zurich hospitality.",
                        href: item.latest_tour_leg_id ? `/tour-legs/${item.latest_tour_leg_id}` : undefined,
                      }}
                      primaryActionSlot={
                        item.latest_tour_leg_id ? undefined : (
                          <TourLegButton clusterId={item.cluster.id} className="ghost-button" label="Build route and cost review" />
                        )
                      }
                    />
                  ) : null}
                </div>
              ) : (
                <ActionNotice
                  severity="warning"
                  title="Cost estimate needs route data"
                  explanation="Roadshow could not recognize enough itinerary context to produce a useful internal logistics estimate."
                  primaryAction={{
                    label: item.latest_tour_leg_id ? "Open route and cost review" : "Build route and cost review",
                    consequence: item.latest_tour_leg_id
                      ? "Opens the modeled tour leg so you can inspect unresolved route inputs."
                      : "Attempts to build a KOF stop and surfaces any missing route data directly.",
                    href: item.latest_tour_leg_id ? `/tour-legs/${item.latest_tour_leg_id}` : undefined,
                  }}
                  primaryActionSlot={
                    item.latest_tour_leg_id ? undefined : (
                      <TourLegButton clusterId={item.cluster.id} className="ghost-button" label="Build route and cost review" />
                    )
                  }
                  secondaryActions={[
                    {
                      label: "Inspect speaker evidence",
                      consequence: "Opens the speaker dossier where missing affiliation or itinerary facts can be corrected.",
                      href: `/researchers/${item.researcher.id}`,
                    },
                  ]}
                />
              )}
            </div>

            <div className="opportunity-section">
              <h3>Why it ranks</h3>
              <AiResearchFitButton className="ghost-button" clusterId={item.cluster.id} />
              <div className="timeline-strip">
                {item.draft_count > 0 ? (
                  <span className="timeline-chip">
                    {item.draft_count} draft{item.draft_count === 1 ? "" : "s"}
                  </span>
                ) : null}
                {item.cluster.rationale.map((entry) => (
                  <span className="timeline-chip" key={`${item.cluster.id}-${entry.label}`} title={entry.detail}>
                    {entry.ai_generated ? `${entry.label}` : `${entry.label} +${entry.points}`}
                  </span>
                ))}
              </div>
              <div className="card-list compact-list">
                {item.cluster.rationale
                  .filter((entry) => entry.detail && (entry.points > 0 || entry.ai_generated || entry.label === "AI Research Fit Explanation"))
                  .map((entry) => (
                    <div className="list-card" key={`${item.cluster.id}-${entry.label}-detail`}>
                      <strong>{entry.label}</strong>
                      <p className="muted">{entry.detail}</p>
                      {entry.ai_status ? <p className="fine-print">AI status: {entry.ai_status}</p> : null}
                    </div>
                  ))}
              </div>
              {item.cluster.uses_unreviewed_evidence ? (
                <ActionNotice
                  severity="warning"
                  title="Evidence review affects this score"
                  explanation="One or more ranking signals came from unapproved fact candidates, so outreach still needs a human evidence decision."
                  primaryAction={{
                    label: "Approve evidence for outreach",
                    consequence: "Opens the pending evidence queue for this speaker so the score and draft gate can be cleared.",
                    href: `/review?status=pending&researcher_id=${item.researcher.id}`,
                  }}
                  secondaryActions={[
                    {
                      label: "Search trusted evidence",
                      consequence: "Opens the speaker dossier where Roadshow can search trusted sources and add candidates.",
                      href: `/researchers/${item.researcher.id}#manual-facts`,
                    },
                  ]}
                />
              ) : null}
            </div>

            <div className="opportunity-actions">
                    <Link className="ghost-button" href={`/researchers/${item.researcher.id}`}>
                Inspect speaker evidence
              </Link>
              {item.latest_draft_id ? (
                <Link className="ghost-button" href={`/drafts/${item.latest_draft_id}`}>
                  Inspect prepared draft
                </Link>
              ) : null}
              {!item.route_review_action && item.latest_tour_leg_id ? (
                <Link className="ghost-button" href={`/tour-legs/${item.latest_tour_leg_id}`}>
                  Inspect route review
                </Link>
              ) : null}
              {!item.route_review_action && !item.latest_tour_leg_id ? <TourLegButton clusterId={item.cluster.id} /> : null}
              {item.draft_ready ? (
                <div className="template-actions">
                  <DraftButton
                    researcherId={item.researcher.id}
                    clusterId={item.cluster.id}
                    label="Create AI-assisted KOF draft"
                    useAi
                  />
                </div>
              ) : (
                <ActionNotice
                  severity="blocked"
                  title="Draft blocked"
                  explanation={firstDraftBlocker(item).message}
                  primaryAction={{
                    label: firstDraftBlocker(item).action_label,
                    consequence: "Opens the exact evidence or speaker record needed before Roadshow can create the invitation.",
                    href: firstDraftBlocker(item).action_href,
                  }}
                  secondaryActions={blockerActions(item)
                    .slice(1)
                    .map((blocker) => ({
                      label: blocker.action_label,
                      consequence: blocker.message,
                      href: blocker.action_href,
                    }))}
                />
              )}
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
