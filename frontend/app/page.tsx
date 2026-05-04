import type { Route } from "next";
import Link from "next/link";

import { ActionNotice } from "@/components/action-notice";
import { AiAutopilotPlanButton } from "@/components/ai-autopilot-plan-button";
import { ApiOfflineState } from "@/components/api-offline-state";
import { BusinessCaseRunButton } from "@/components/business-case-run-button";
import { MorningSweepButton } from "@/components/morning-sweep-button";
import { Panel } from "@/components/panel";
import { getBusinessCaseRuns, getOperatorCockpit, type BusinessCaseRun, type OperatorPrimaryFlow, type OperatorSetupBlocker } from "@/lib/server-api";

export const dynamic = "force-dynamic";

const DATA_STATE_COPY = {
  empty: {
    label: "No data yet",
    tone: "blocked",
    text: "Roadshow has no source sync or seminar setup yet. Start with a real source sync and define the weekly KOF slot if needed.",
  },
  demo: {
    label: "Unverified records present",
    tone: "warning",
    text: "Some records were created outside the normal source-sync path. Run source sync and verify evidence before outreach.",
  },
  real: {
    label: "Real scraper data available",
    tone: "",
    text: "Roadshow has live or manually entered records and can guide seminar decisions from the current database.",
  },
  stale: {
    label: "Sources stale",
    tone: "blocked",
    text: "At least one watched source needs action. Refresh source data before relying on the opportunity picture.",
  },
} as const;

function metricValue(metrics: Record<string, number>, key: string): number {
  return metrics[key] ?? 0;
}

function workspaceLabel(href?: string | null): string {
  if (!href) {
    return "Start";
  }
  if (href.startsWith("/seminar-admin")) {
    return "Settings";
  }
  if (href.startsWith("/review")) {
    return "Evidence";
  }
  if (href.startsWith("/calendar")) {
    return "Calendar";
  }
  if (href.startsWith("/drafts")) {
    return "Drafts";
  }
  if (href.startsWith("/opportunities")) {
    return "Opportunities";
  }
  return "Details";
}

function PrimaryAction({ flow }: { flow: OperatorPrimaryFlow }) {
  if (flow.disabled_reason) {
    return (
      <div className="purpose-action">
        <button disabled type="button">
          {flow.label}
        </button>
        <span className="fine-print action-blocker">{flow.disabled_reason}</span>
      </div>
    );
  }
  if (flow.action_key === "morning_sweep" || flow.action_key === "real_sync") {
    return <MorningSweepButton helperText={flow.consequence} label={flow.label} />;
  }
  if (flow.href) {
    return (
      <Link className="button-link" href={flow.href as Route}>
        {flow.label}
      </Link>
    );
  }
  return <span className="timeline-chip">{flow.label}</span>;
}

function BlockerAction({ action }: { action: OperatorPrimaryFlow }) {
  if (action.disabled_reason) {
    return (
      <div className="purpose-action">
        <button disabled type="button">
          {action.label}
        </button>
        <span className="fine-print action-blocker">{action.disabled_reason}</span>
      </div>
    );
  }
  if (action.action_key === "morning_sweep" || action.action_key === "real_sync") {
    return <MorningSweepButton helperText={action.consequence} label={action.label} />;
  }
  if (action.href) {
    return (
      <Link className="button-link" href={action.href as Route}>
        {action.label}
      </Link>
    );
  }
  return <span className="timeline-chip">{action.label}</span>;
}

function BlockerList({ blockers }: { blockers: OperatorSetupBlocker[] }) {
  if (!blockers.length) {
    return (
      <div className="empty-state">
        <h3>No setup blockers.</h3>
        <p className="muted">KOF slots, speaker visits, evidence, and source state are ready enough for normal seminar work.</p>
      </div>
    );
  }
  return (
    <div className="guided-list">
      {blockers.map((blocker, index) => (
        <article className="guided-item" key={blocker.id}>
          <span className="step-index">{index + 1}</span>
          <div>
            <h3>{blocker.title}</h3>
            <p className="muted">{blocker.explanation}</p>
            <p className="fine-print">
              Handle this in {workspaceLabel(blocker.action.href)}. {blocker.action.consequence}
            </p>
            <div className="blocker-action-row">
              <BlockerAction action={blocker.action} />
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function RecentChangeList({ changes }: { changes: { id: string; event_type: string; created_at: string }[] }) {
  if (!changes.length) {
    return (
      <div className="empty-state">
        <h3>No actions recorded yet.</h3>
        <p className="muted">Source syncs, evidence decisions, drafts, and tour proposals will appear here.</p>
      </div>
    );
  }
  return (
    <div className="guided-list compact">
      {changes.slice(0, 4).map((event) => (
        <article className="guided-item" key={event.id}>
          <span className="status-pill">{event.event_type.replaceAll("_", " ")}</span>
          <p className="muted">{new Date(event.created_at).toLocaleString()}</p>
        </article>
      ))}
    </div>
  );
}

function DataStateNotice({ dataState }: { dataState: (typeof DATA_STATE_COPY)[keyof typeof DATA_STATE_COPY] }) {
  if (!dataState.tone) {
    return (
      <div className="data-state-banner">
        <span className="status-pill">{dataState.label}</span>
        <p>{dataState.text}</p>
      </div>
    );
  }

  const isStale = dataState.label === "Sources stale";
  return (
    <ActionNotice
      severity={dataState.tone}
      title={dataState.label}
      explanation={dataState.text}
      primaryAction={{
        label: isStale ? "Inspect data sources" : "Run real source sync",
        consequence: isStale
          ? "Opens the exact source status page with failure reasons, official links, and parser state."
          : "Refreshes watched sources, KOF calendar, evidence, availability, scores, and source status.",
        href: isStale ? "/source-health" : undefined,
      }}
      primaryActionSlot={
        isStale ? undefined : (
          <MorningSweepButton helperText="Refreshes watched sources, KOF calendar, evidence, availability, scores, and source status." />
        )
      }
      secondaryActions={[
        {
          label: "Set weekly KOF slot",
          consequence: "Opens KOF slot settings so source data can be matched against actual seminar capacity.",
          href: "/seminar-admin",
        },
      ]}
    />
  );
}

function SourceStatusNotice({
  sourcesNeedingAttention,
  needsAdapter,
}: {
  sourcesNeedingAttention: number;
  needsAdapter: number;
}) {
  if (!sourcesNeedingAttention && !needsAdapter) {
    return null;
  }
  return (
    <ActionNotice
      severity="warning"
      title="Some watched sources need action"
      explanation="The current opportunity picture may be incomplete until source errors, empty feeds, or adapter gaps are inspected."
      primaryAction={{
        label: "Run real source sync",
        consequence: "Re-checks watched sources and records a new source-health snapshot.",
      }}
      primaryActionSlot={<MorningSweepButton helperText="Re-checks watched sources and records a new source-health snapshot." />}
      secondaryActions={[
        {
          label: "Inspect data sources",
          consequence: "Shows the exact failing or empty source, latest error, official source link, and parser strategy.",
          href: "/source-health",
        },
      ]}
    />
  );
}

function BusinessCaseStatus({ run }: { run?: BusinessCaseRun | null }) {
  if (!run) {
    return (
      <ActionNotice
        explanation="No real-case shadow audit has been recorded yet."
        severity="info"
        title="Business-case quality gate not run"
        primaryAction={{
          label: "Open business-case audit",
          consequence: "Opens the audit page for Mirko Wiederholt, Rahul Deb, Daron Acemoglu, and a real-data negative control.",
          href: "/business-cases",
        }}
      />
    );
  }
  const blocked = typeof run.summary_json.blocked_count === "number" ? run.summary_json.blocked_count : 0;
  const allowed = typeof run.summary_json.draft_allowed_count === "number" ? run.summary_json.draft_allowed_count : 0;
  const severity = run.status === "failed" ? "error" : blocked ? "warning" : "info";
  return (
    <ActionNotice
      explanation={`Latest audit tested ${run.results.length} cases. ${allowed} draft previews passed, ${blocked} cases are blocked with explicit reasons.`}
      severity={severity}
      title="Latest business-case audit"
      primaryAction={{
        label: "Inspect business-case blockers",
        consequence: "Opens the latest case audit with evidence, KOF fit, route, fare, and draft-gate details.",
        href: "/business-cases",
      }}
    />
  );
}

export default async function HomePage() {
  let cockpit;
  let businessRuns: BusinessCaseRun[] = [];
  try {
    cockpit = await getOperatorCockpit();
    businessRuns = await getBusinessCaseRuns();
  } catch (error) {
    return <ApiOfflineState message={error instanceof Error ? error.message : "Roadshow API is unavailable."} />;
  }

  const dataState = DATA_STATE_COPY[cockpit.data_state] ?? DATA_STATE_COPY.empty;

  return (
    <div className="stack">
      <section className="hero guided-hero">
        <div className="hero-card guided-start-card">
          <span className="eyebrow">Seminar Manager Start</span>
          <h1 className="hero-title">One next seminar action, not another dashboard.</h1>
          <p className="hero-copy">
            Roadshow checks whether KOF has slots, whether speaker visits exist, whether evidence blocks outreach, and what you should do next.
          </p>
          <DataStateNotice dataState={dataState} />
        </div>

        <section className="primary-flow-card" data-primary-action="true">
          <span className="eyebrow">Next action</span>
          <h2>{cockpit.primary_flow.label}</h2>
          <p>{cockpit.primary_flow.consequence}</p>
          <PrimaryAction flow={cockpit.primary_flow} />
          <AiAutopilotPlanButton className="ghost-button" />
        </section>
      </section>

      <section className="guided-metrics" aria-label="What Roadshow knows">
        <div className="metric">
          <div className="metric-value">{metricValue(cockpit.summary_metrics, "active_kof_slots")}</div>
          <div className="metric-label">Weekly KOF slot patterns</div>
        </div>
        <div className="metric">
          <div className="metric-value">{metricValue(cockpit.summary_metrics, "open_windows")}</div>
          <div className="metric-label">Open KOF windows</div>
        </div>
        <div className="metric">
          <div className="metric-value">{metricValue(cockpit.summary_metrics, "speaker_visits")}</div>
          <div className="metric-label">Speaker visits found</div>
        </div>
        <div className="metric">
          <div className="metric-value">{metricValue(cockpit.summary_metrics, "pending_evidence")}</div>
          <div className="metric-label">Evidence items to approve</div>
        </div>
      </section>

      <Panel title="Source status" copy="The latest real-data picture from watched institutions and KOF calendar sync.">
        <div className="guided-metrics compact">
          <div className="metric">
            <div className="metric-value">{cockpit.source_snapshot.sources_tracked}</div>
            <div className="metric-label">Sources tracked</div>
          </div>
          <div className="metric">
            <div className="metric-value">{cockpit.source_snapshot.sources_with_events}</div>
            <div className="metric-label">Sources with events</div>
          </div>
          <div className="metric">
            <div className="metric-value">{cockpit.source_snapshot.total_events_last_check}</div>
            <div className="metric-label">Events in latest checks</div>
          </div>
          <div className="metric">
            <div className="metric-value">{cockpit.source_snapshot.sources_needing_attention}</div>
            <div className="metric-label">Sources needing attention</div>
          </div>
        </div>
        <p className="fine-print">
          Last source sync:{" "}
          {cockpit.source_snapshot.last_sync_at ? new Date(cockpit.source_snapshot.last_sync_at).toLocaleString() : "not recorded yet"}.
          {cockpit.source_snapshot.needs_adapter
            ? ` ${cockpit.source_snapshot.needs_adapter} watched source${cockpit.source_snapshot.needs_adapter === 1 ? "" : "s"} still need source-specific extraction.`
            : ""}
        </p>
        <SourceStatusNotice
          needsAdapter={cockpit.source_snapshot.needs_adapter}
          sourcesNeedingAttention={cockpit.source_snapshot.sources_needing_attention}
        />
      </Panel>

      <section className="dual-grid">
        <Panel title="What blocks seminar management" copy="This is the checklist behind the one recommended action above.">
          <BlockerList blockers={cockpit.setup_blockers} />
        </Panel>
        <Panel title="What changed recently" copy="A short audit trail so you can re-enter the workflow quickly.">
          <RecentChangeList changes={cockpit.recent_changes} />
        </Panel>
      </section>

      <Panel title="Business-case quality gate" copy="A compact proof check for real target cases before Roadshow is trusted for outreach decisions.">
        <BusinessCaseStatus run={businessRuns[0]} />
        <BusinessCaseRunButton onCompleteHref="/business-cases" />
      </Panel>

      <Panel title="Workspaces" copy="Use these only when the next action points you there, or when you want to inspect details.">
        <div className="workspace-grid">
          <Link className="workspace-link" href="/opportunities">
            <strong>Opportunities</strong>
            <span>Ranked speaker visits, best KOF slot, cost split, and draft readiness.</span>
          </Link>
          <Link className="workspace-link" href="/calendar">
            <strong>Calendar</strong>
            <span>KOF occupied events and generated open invitation windows.</span>
          </Link>
          <Link className="workspace-link" href="/review?status=pending">
            <strong>Evidence</strong>
            <span>Approve PhD and nationality facts before outreach uses them.</span>
          </Link>
          <Link className="workspace-link" href="/drafts">
            <strong>Drafts</strong>
            <span>Generated invitations awaiting human review or manual send tracking.</span>
          </Link>
          <Link className="workspace-link" href="/seminar-admin">
            <strong>Settings</strong>
            <span>Recurring KOF seminar slots, manual blocks, and one-off openings.</span>
          </Link>
          <Link className="workspace-link" href={"/business-cases" as Route}>
            <strong>Business Case Audit</strong>
            <span>Shadow-test real target cases across data, fit, route, fare, and draft gates.</span>
          </Link>
        </div>
      </Panel>
    </div>
  );
}
