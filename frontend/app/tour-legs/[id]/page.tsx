import Link from "next/link";

import { ActionNotice } from "@/components/action-notice";
import { FeedbackSignalForm } from "@/components/feedback-signal-form";
import { Panel } from "@/components/panel";
import { RefreshPricesButton } from "@/components/refresh-prices-button";
import { getInstitutions, getTourLeg } from "@/lib/server-api";

export const dynamic = "force-dynamic";

type TourLegPageProps = {
  params: Promise<{ id: string }>;
};

function asMoney(value: number): string {
  return `CHF ${value.toLocaleString()}`;
}

function honorariumLabel(value: number): string {
  return value > 0 ? asMoney(value) : "Not assumed";
}

function costComponents(value: Record<string, unknown>): Array<Record<string, unknown>> {
  return Array.isArray(value.components) ? (value.components as Array<Record<string, unknown>>) : [];
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    cached: "Cached fare",
    estimate_requires_review: "Estimate needs review",
    failed: "Fare check failed",
    hospitality_estimate: "Hospitality estimate",
    live: "Live fare",
    not_rail_priced: "Not rail priced",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function statusTone(status: string): string {
  if (status === "live" || status === "cached" || status === "hospitality_estimate") {
    return "";
  }
  if (status === "estimate_requires_review" || status === "not_rail_priced") {
    return "warning";
  }
  return "blocked";
}

function providerLabel(value: unknown): string {
  return String(value || "Roadshow estimate").replaceAll("_", " ");
}

function policyLabel(component: Record<string, unknown>): string | null {
  const fareClass = String(component.fare_class || "");
  const farePolicy = String(component.fare_policy || "");
  if (!fareClass && !farePolicy) {
    return null;
  }
  const classLabel = fareClass === "first" ? "1st class" : `${fareClass || "rail"} class`;
  return `${classLabel} ${farePolicy.replaceAll("_", " ") || "fare"}`.trim();
}

function isHospitality(component: Record<string, unknown>): boolean {
  return component.category === "zurich_hospitality" || component.price_status === "hospitality_estimate";
}

function isUncertainFare(component: Record<string, unknown>): boolean {
  return ["estimate_requires_review", "failed", "manual_review", "not_rail_priced"].includes(String(component.price_status || ""));
}

function itemLabel(value: string): string {
  return value.replace(/_chf$/, "").replaceAll("_", " ");
}

function hospitalityItems(component: Record<string, unknown>): Array<[string, number]> {
  const items = component.items;
  if (!items || typeof items !== "object" || Array.isArray(items)) {
    return [];
  }
  return Object.entries(items as Record<string, unknown>).map(([key, value]) => [itemLabel(key), Number(value || 0)]);
}

export default async function TourLegPage({ params }: TourLegPageProps) {
  const { id } = await params;
  const [tourLeg, institutions] = await Promise.all([getTourLeg(id), getInstitutions()]);
  const kof = institutions.find((institution) => institution.name.includes("KOF")) ?? institutions[0];
  const components = costComponents(tourLeg.cost_split_json);

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
            <div className="metric-value">{honorariumLabel(tourLeg.estimated_fee_total_chf)}</div>
            <div className="metric-label">Explicit honorarium</div>
          </div>
          <div className="metric">
            <div className="metric-value">{asMoney(tourLeg.estimated_travel_total_chf)}</div>
            <div className="metric-label">Modeled logistics</div>
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
                  <span className="timeline-chip">Honorarium {honorariumLabel(stop.fee_chf)}</span>
                  <span className="timeline-chip">Host logistics {asMoney(stop.travel_share_chf)}</span>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          title="Cost split"
          copy="Rail rows use KOF's 1st class full-fare planning policy. Fare details stay internal and never appear in speaker invitations."
          rightSlot={<RefreshPricesButton tourLegId={tourLeg.id} />}
        >
          <div className="card-list">
            {components.length ? (
              components.map((component, index) => {
                const priceStatus = String(component.price_status || (isHospitality(component) ? "hospitality_estimate" : "estimate_requires_review"));
                const policy = policyLabel(component);
                const bookingHref = typeof component.action_href === "string" ? component.action_href : null;
                return (
                  <div className="list-card" key={`${String(component.category)}-${index}`}>
                    <div className="panel-header">
                      <div>
                        <h3>{String(component.payer ?? "Host responsibility")}</h3>
                        <p className="muted">{String(component.route ?? "")}</p>
                      </div>
                      <span className={`status-pill ${statusTone(priceStatus)}`}>{statusLabel(priceStatus)}</span>
                    </div>
                    <div className="timeline-strip">
                      <span className="timeline-chip">{asMoney(Number(component.amount_chf ?? 0))}</span>
                      {policy ? <span className="timeline-chip">{policy}</span> : null}
                      <span className="timeline-chip">{providerLabel(component.provider)}</span>
                    </div>
                    {isHospitality(component) && hospitalityItems(component).length ? (
                      <div className="timeline-strip">
                        {hospitalityItems(component).map(([label, amount]) => (
                          <span className="timeline-chip" key={`${String(component.category)}-${label}`}>
                            {label} {asMoney(amount)}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {component.last_checked_at ? (
                      <p className="fine-print">Last checked: {new Date(String(component.last_checked_at)).toLocaleString()}</p>
                    ) : null}
                    <p className="fine-print">{String(component.responsibility ?? "")}</p>
                    {!isHospitality(component) && isUncertainFare(component) ? (
                      <ActionNotice
                        severity={priceStatus === "failed" ? "error" : "warning"}
                        title="Fare estimate needs action"
                        explanation="Roadshow is using a conservative internal estimate until an authorized first-class fare check succeeds or is manually verified."
                        primaryAction={{
                          label: component.price_check_id ? "Refresh first-class fare" : "Check first-class fare",
                          consequence: "Retries authorized fare providers and updates the tour leg cost split with cached evidence.",
                        }}
                        primaryActionSlot={
                          <RefreshPricesButton
                            className="ghost-button"
                            helperText="Retries authorized fare providers; fallback estimates remain marked for review."
                            label={component.price_check_id ? "Refresh first-class fare" : "Check first-class fare"}
                            tourLegId={tourLeg.id}
                          />
                        }
                        secondaryActions={
                          bookingHref
                            ? [
                                {
                                  label: "Open booking source",
                                  consequence: "Opens the provider page for manual fare verification outside Roadshow.",
                                  href: bookingHref,
                                  external: true,
                                },
                              ]
                            : []
                        }
                      />
                    ) : null}
                  </div>
                );
              })
            ) : (
              <div className="list-card">
                <h3>Deterministic split</h3>
                <p className="fine-print">No detailed cost components are attached to this older tour leg.</p>
                <ActionNotice
                  severity="info"
                  title="Cost components can be refreshed"
                  explanation="Older tour legs remain readable, but price evidence appears only after Roadshow refreshes rail components."
                  primaryAction={{
                    label: "Refresh first-class fares",
                    consequence: "Rebuilds price checks and attaches auditable cost components where route data is available.",
                  }}
                  primaryActionSlot={
                    <RefreshPricesButton
                      helperText="Rebuilds price checks and attaches auditable cost components where route data is available."
                      label="Refresh first-class fares"
                      tourLegId={tourLeg.id}
                    />
                  }
                />
              </div>
            )}
            <div className="list-card">
              <h3>Honorarium</h3>
              <p className="fine-print">
                {tourLeg.estimated_fee_total_chf > 0
                  ? `${asMoney(tourLeg.estimated_fee_total_chf)} from ${String(tourLeg.cost_split_json.speaker_fee_source ?? "configured source")}.`
                  : "No speaker fee or honorarium is assumed for this proposal."}
              </p>
            </div>
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
