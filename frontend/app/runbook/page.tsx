import Link from "next/link";

import { Panel } from "@/components/panel";
import { SourceJobRunner } from "@/components/source-job-runner";
import { getOperatorRunbook, type RunbookStep } from "@/lib/api";

function statusTone(status: string): string {
  if (status === "blocked" || status === "needs_attention") {
    return "blocked";
  }
  return "";
}

function statusLabel(status: string): string {
  return status.replace("_", " ");
}

function draftStatusLabel(status: string): string {
  return status
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function stepHref(step: RunbookStep): "/source-health" | "/review" | "/opportunities" | "/drafts" {
  if (step.key === "source-audit") {
    return "/source-health";
  }
  if (step.key === "fact-review") {
    return "/review";
  }
  if (step.key === "opportunities") {
    return "/opportunities";
  }
  return "/drafts";
}

function RunbookStepCard({ step, index }: { step: RunbookStep; index: number }) {
  return (
    <article className="runbook-step list-card">
      <div className="runbook-step-number">{index + 1}</div>
      <div className="stack">
        <div className="panel-header">
          <div>
            <h3>{step.title}</h3>
            <p className="muted">{step.detail}</p>
          </div>
          <span className={`status-pill ${statusTone(step.status)}`}>{statusLabel(step.status)}</span>
        </div>
        <div className="opportunity-actions">
          <span className="timeline-chip">{step.count} related item{step.count === 1 ? "" : "s"}</span>
          <Link className="ghost-button" href={stepHref(step)}>
            {step.cta_label}
          </Link>
        </div>
      </div>
    </article>
  );
}

export default async function RunbookPage() {
  const runbook = await getOperatorRunbook();
  const draftStatuses = Object.entries(runbook.draft_counts_by_status).sort(([left], [right]) => left.localeCompare(right));
  const attentionTotal = runbook.source_attention_count + runbook.pending_fact_count;

  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Daily Operator Runbook</span>
          <h1 className="hero-title">Start here, then work the queue.</h1>
          <p className="hero-copy">
            This page condenses source health, evidence review, open seminar supply, opportunity readiness, and draft lifecycle follow-up into
            one operating sequence for KOF admins.
          </p>
          <div className="kpi-grid">
            <div className="metric">
              <div className="metric-value">{runbook.source_attention_count}</div>
              <div className="metric-label">Source signals to inspect</div>
            </div>
            <div className="metric">
              <div className="metric-value">{runbook.pending_fact_count}</div>
              <div className="metric-label">Fact candidates pending</div>
            </div>
            <div className="metric">
              <div className="metric-value">{runbook.draft_ready_opportunity_count}</div>
              <div className="metric-label">Draft-ready opportunities</div>
            </div>
            <div className="metric">
              <div className="metric-value">{runbook.open_window_count}</div>
              <div className="metric-label">Open KOF windows</div>
            </div>
          </div>
        </div>
        <Panel title="Today's posture" copy="A lightweight health read before the concierge desk starts moving names.">
          <div className="card-list">
            <div className="list-card">
              <h3>{attentionTotal ? "Human attention is useful" : "The desk is clear"}</h3>
              <p className="muted">
                {attentionTotal
                  ? "Review source anomalies and pending evidence before generating new outreach."
                  : "No source or evidence blockers are currently flagged by the runbook."}
              </p>
            </div>
            <div className="list-card">
              <h3>{runbook.host_event_count} occupied KOF events</h3>
              <p className="muted">These public calendar events are subtracted from admin-defined seminar templates.</p>
            </div>
          </div>
        </Panel>
      </section>

      <section className="dual-grid">
        <Panel title="Run sync jobs" copy="Kick the data layer before making invitation decisions.">
          <SourceJobRunner />
        </Panel>
        <Panel title="Draft lifecycle" copy="Generated drafts should move from draft to reviewed, sent, or archived.">
          <div className="timeline-strip">
            {draftStatuses.map(([status, count]) => (
              <Link className="timeline-chip" href={{ pathname: "/drafts", query: { status } }} key={status}>
                {draftStatusLabel(status)}: {count}
              </Link>
            ))}
          </div>
        </Panel>
      </section>

      <Panel title="Recommended sequence" copy="The runbook orders the daily work from data freshness to final outreach follow-up.">
        <div className="runbook-grid">
          {runbook.recommended_steps.map((step, index) => (
            <RunbookStepCard index={index} key={step.key} step={step} />
          ))}
        </div>
      </Panel>
    </div>
  );
}
