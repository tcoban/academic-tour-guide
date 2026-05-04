import Link from "next/link";

import { ActionNotice, type ActionNoticeAction } from "@/components/action-notice";
import { Panel } from "@/components/panel";
import { TourAssemblyDraftButton } from "@/components/tour-assembly-actions";
import { getTourAssembly } from "@/lib/api";

export const dynamic = "force-dynamic";

type TourAssemblyPageProps = {
  params: Promise<{ id: string }>;
};

function asMoney(value: unknown): string {
  return typeof value === "number" ? `CHF ${value.toLocaleString()}` : "Pending";
}

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asText(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(" ");
  }
  if (typeof value === "object" && value !== null) {
    return JSON.stringify(value);
  }
  return String(value ?? "Pending");
}

function blockerAction(code: string, researcherId?: string | null): ActionNoticeAction {
  if (code === "speaker_fee_floor_missing") {
    return {
      label: "Update speaker profile",
      consequence: "Opens the speaker dossier where fee-floor assumptions can be entered or removed from the assembly gate.",
      href: researcherId ? `/researchers/${researcherId}` : "/wishlist",
    };
  }
  if (code === "trip_cluster_missing") {
    return {
      label: "Run real source sync",
      consequence: "Returns to Start so Scout can search for current trip clusters before the speaker tour is drafted.",
      href: "/",
    };
  }
  if (code === "researcher_identity_missing") {
    return {
      label: "Link speaker identity",
      consequence: "Opens Wishlist so the matched speaker can be connected to a researcher record.",
      href: "/wishlist",
    };
  }
  if (code.startsWith("host_budget")) {
    return {
      label: "Update host budget profile",
      consequence: "Opens Wishlist context so the host budget profile can be completed before the anonymous proposal advances.",
      href: "/wishlist",
    };
  }
  return {
    label: "Inspect assembly proposal",
    consequence: "Keeps you on this proposal so the blocker can be resolved from the relevant workspace link.",
    href: "#assembly-blockers",
  };
}

export default async function TourAssemblyPage({ params }: TourAssemblyPageProps) {
  const { id } = await params;
  const proposal = await getTourAssembly(id);
  const blockers = proposal.blockers.map((blocker) => ({
    code: String(blocker.code ?? "assembly_blocker"),
    detail: String(blocker.detail ?? blocker.code ?? "Assembly action required"),
  }));
  const disabledReason = blockers.length ? blockers.map((blocker) => blocker.detail).join(" ") : null;
  const hostCount = asNumber(proposal.masked_summary_json.participant_count ?? proposal.budget_summary_json.host_count);

  return (
    <div className="stack">
      <Panel
        title={proposal.title}
        copy={`${proposal.status} | ${hostCount} masked hosts`}
        rightSlot={<Link className="ghost-button" href="/tour-assemblies">Back to assemblies</Link>}
      >
        <div className="kpi-grid">
          <div className="metric">
            <div className="metric-value">{hostCount}</div>
            <div className="metric-label">Masked hosts</div>
          </div>
          <div className="metric">
            <div className="metric-value">{asMoney(proposal.budget_summary_json.per_host_total_estimate_chf)}</div>
            <div className="metric-label">Per-host estimate</div>
          </div>
          <div className="metric">
            <div className="metric-value">{proposal.blockers.length}</div>
            <div className="metric-label">Review blockers</div>
          </div>
        </div>
      </Panel>

      <section className="dual-grid">
        <Panel title="Masked stops" copy="Co-host identities stay private; Roadshow shows labels, regions, budget status, and order.">
          <div className="card-list">
            {(proposal.masked_summary_json.ordered_stops ?? []).map((stop, index) => (
              <div className="list-card" key={`${proposal.id}-stop-${index}`}>
                <div className="panel-header">
                  <div>
                    <h3>
                      {String(stop.sequence ?? index + 1)}. {String(stop.masked_label ?? "Masked host")}
                    </h3>
                    <p className="muted">
                      {String(stop.city_region ?? "Region pending")} | target {String(stop.target_date ?? "date pending")}
                    </p>
                  </div>
                  <span className="status-pill">{asMoney(stop.travel_share_chf)}</span>
                </div>
                <p className="fine-print">Speaker fee {asMoney(stop.fee_chf)} plus deterministic travel share.</p>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Cost split" copy="Deterministic screening only; the app does not quote fares or move money.">
          <div className="card-list">
            {Object.entries(proposal.budget_summary_json).map(([key, value]) => (
              <div className="list-card" key={key}>
                <h3>{key.replaceAll("_", " ")}</h3>
                <p className="fine-print">{asText(value)}</p>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      <section className="dual-grid">
        <Panel title="Term sheet" copy="Private admin-facing terms before any speaker request is generated.">
          <div className="card-list">
            {Object.entries(proposal.term_sheet_json).map(([key, value]) => (
              <div className="list-card" key={key}>
                <h3>{key.replaceAll("_", " ")}</h3>
                <p className="fine-print">{asText(value)}</p>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Next speaker action" copy="Create the multi-host request only after blockers and approved evidence are clear.">
          {proposal.speaker_draft_id ? (
            <Link className="primary-button" href={`/drafts/${proposal.speaker_draft_id}`}>
              Inspect speaker tour draft
            </Link>
          ) : (
            <TourAssemblyDraftButton proposalId={proposal.id} disabledReason={disabledReason} />
          )}
          {blockers.length ? (
            <div className="card-list" id="assembly-blockers">
              {blockers.map((blocker, index) => (
                <ActionNotice
                  severity="blocked"
                  title={`Assembly blocker ${index + 1}`}
                  explanation={blocker.detail}
                  key={`${proposal.id}-blocker-${index}`}
                  primaryAction={blockerAction(blocker.code, proposal.researcher_id)}
                  secondaryActions={[
                    {
                      label: "Inspect wishlist matches",
                      consequence: "Shows the masked co-host context that produced this proposal.",
                      href: "/wishlist",
                    },
                  ]}
                />
              ))}
            </div>
          ) : (
            <p className="fine-print">No proposal blockers are recorded. Biographic evidence is still checked by the draft endpoint.</p>
          )}
        </Panel>
      </section>
    </div>
  );
}
