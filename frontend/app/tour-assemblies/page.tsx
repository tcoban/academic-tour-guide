import Link from "next/link";

import { ActionNotice } from "@/components/action-notice";
import { Panel } from "@/components/panel";
import { getTourAssemblies } from "@/lib/server-api";

export const dynamic = "force-dynamic";

function asMoney(value: unknown): string {
  return typeof value === "number" ? `CHF ${value.toLocaleString()}` : "Pending";
}

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export default async function TourAssembliesPage() {
  const proposals = await getTourAssemblies();
  const blocked = proposals.filter((proposal) => proposal.status === "blocked").length;
  const ready = proposals.filter((proposal) => proposal.status === "ready_for_review").length;

  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Anonymous Tour Assembly</span>
          <h1 className="hero-title">Turn shared wishlists into masked speaker tours.</h1>
          <p className="hero-copy">
            Roadshow keeps co-host identities private while it checks speaker fit, host budget, ordered stops, and review blockers.
          </p>
          <div className="kpi-grid">
            <div className="metric">
              <div className="metric-value">{proposals.length}</div>
              <div className="metric-label">Tour assemblies</div>
            </div>
            <div className="metric">
              <div className="metric-value">{ready}</div>
              <div className="metric-label">Ready for draft</div>
            </div>
            <div className="metric">
              <div className="metric-value">{blocked}</div>
              <div className="metric-label">Blocked</div>
            </div>
          </div>
        </div>
        <Panel title="How assemblies start" copy="Use Wishlist and build a proposal from an anonymous co-host match.">
          <Link className="ghost-button" href="/wishlist">
            Inspect wishlist matches
          </Link>
        </Panel>
      </section>

      <Panel title="Assembly ledger" copy="Masked proposals only; no institution messaging, contract, payment, or booking is executed here.">
        <div className="card-list">
          {proposals.length ? (
            proposals.map((proposal) => (
              <div className="list-card" key={proposal.id}>
                <div className="panel-header">
                  <div>
                    <h3>{proposal.title}</h3>
                    <p className="muted">
                      {asNumber(proposal.masked_summary_json.participant_count ?? proposal.budget_summary_json.host_count)} masked hosts |{" "}
                      {asMoney(proposal.budget_summary_json.per_host_total_estimate_chf)} per host
                    </p>
                  </div>
                  <span className="status-pill">{proposal.status}</span>
                </div>
                <div className="timeline-strip">
                  {(proposal.masked_summary_json.participants ?? []).slice(0, 4).map((participant, index) => (
                    <span className="timeline-chip" key={`${proposal.id}-${index}`}>
                      {String(participant.masked_label ?? "Masked host")}: {String(participant.budget_status ?? "budget pending")}
                    </span>
                  ))}
                </div>
                {proposal.blockers.length ? (
                  <ActionNotice
                    severity="blocked"
                    title="Assembly blockers need action"
                    explanation={`${proposal.blockers.length} blocker${proposal.blockers.length === 1 ? "" : "s"} must be cleared before Roadshow can create the speaker tour draft.`}
                    primaryAction={{
                      label: "Inspect assembly blockers",
                      consequence: "Opens the proposal detail with the exact blocker list and resolving workspace links.",
                      href: `/tour-assemblies/${proposal.id}`,
                    }}
                  />
                ) : (
                  <p className="fine-print">Budget and identity checks are ready for speaker-draft review.</p>
                )}
                <div className="template-actions">
                  <Link className="ghost-button" href={`/tour-assemblies/${proposal.id}`}>
                    Inspect assembly proposal
                  </Link>
                </div>
              </div>
            ))
          ) : (
            <ActionNotice
              severity="info"
              title="No anonymous tour assemblies yet"
              explanation="Build the first masked proposal from a co-host match on the Wishlist page."
              primaryAction={{
                label: "Inspect wishlist matches",
                consequence: "Shows anonymous co-host matches that can become tour assemblies.",
                href: "/wishlist",
              }}
            />
          )}
        </div>
      </Panel>
    </div>
  );
}
