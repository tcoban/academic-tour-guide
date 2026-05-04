import type { Route } from "next";
import Link from "next/link";

import { ActionNotice } from "@/components/action-notice";
import { ApiOfflineState } from "@/components/api-offline-state";
import { BusinessCaseRunButton } from "@/components/business-case-run-button";
import { Panel } from "@/components/panel";
import { getBusinessCaseRuns, type BusinessCaseResult, type BusinessCaseRun } from "@/lib/server-api";

export const dynamic = "force-dynamic";

function statusLabel(value: string) {
  return value.replaceAll("_", " ");
}

function verdictTone(verdict: string) {
  if (verdict.includes("allowed")) {
    return "";
  }
  if (verdict === "ready_for_admin_review") {
    return "warning";
  }
  if (verdict.startsWith("blocked")) {
    return "blocked";
  }
  if (verdict.includes("error")) {
    return "error";
  }
  return "warning";
}

function metric(run: BusinessCaseRun | undefined, key: string) {
  const value = run?.summary_json?.[key];
  return typeof value === "number" ? value : 0;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function routeSummary(result: BusinessCaseResult) {
  const travelFit = result.route_summary_json.travel_fit;
  if (travelFit && typeof travelFit === "object" && "summary" in travelFit) {
    return String((travelFit as { summary?: unknown }).summary ?? "");
  }
  if (result.route_status === "no_current_trip") {
    return "No current European planning window was found.";
  }
  if (result.route_status === "no_kof_slot") {
    return "No KOF slot was available for the modeled route.";
  }
  return "Route logic was evaluated by the planner.";
}

function fitSummary(result: BusinessCaseResult) {
  const fit = result.fit_summary_json.matched_kof_research_fit;
  const superstar = Boolean(result.fit_summary_json.superstar_priority);
  const rank = result.fit_summary_json.best_repec_rank;
  if (fit && typeof fit === "object" && "detail" in fit) {
    const detail = String((fit as { detail?: unknown }).detail ?? "");
    return superstar ? `${detail}. Superstar signal is also present.` : detail;
  }
  if (superstar) {
    return typeof rank === "number" ? `RePEc superstar signal found: rank #${rank}.` : "RePEc superstar signal found.";
  }
  return "No deterministic KOF topic or superstar signal was found.";
}

function evidenceSummary(result: BusinessCaseResult) {
  const approved = result.evidence_summary_json.approved_fact_count;
  const pending = result.evidence_summary_json.pending_candidate_count;
  return `${typeof approved === "number" ? approved : 0} approved facts, ${typeof pending === "number" ? pending : 0} pending candidates.`;
}

function CaseSignals({ result }: { result: BusinessCaseResult }) {
  const items = [
    ["Data found", result.data_found ? "ready" : "blocked"],
    ["KOF fit", result.kof_fit_status],
    ["Route plausible", result.route_status],
    ["Evidence approved", result.evidence_status],
    ["Draft allowed", result.draft_status],
  ];
  return (
    <div className="signal-grid">
      {items.map(([label, value]) => (
        <div className="signal-tile" key={label}>
          <span className={`status-pill ${String(value).includes("blocked") || value === "missing" ? "blocked" : ""}`}>
            {statusLabel(String(value))}
          </span>
          <strong>{label}</strong>
        </div>
      ))}
    </div>
  );
}

function BlockerNotices({ result }: { result: BusinessCaseResult }) {
  if (!result.blockers.length) {
    return (
      <div className="empty-state">
        <h3>No blocking action for this case.</h3>
        <p className="muted">Roadshow can explain the outcome from current evidence, route, fit, and draft gate checks.</p>
      </div>
    );
  }
  return (
    <div className="stack tight">
      {result.blockers.map((blocker) => (
        <ActionNotice
          explanation={blocker.explanation}
          key={`${result.id}-${blocker.code}`}
          severity={blocker.code.includes("fare") ? "warning" : "blocked"}
          title={blocker.title}
          primaryAction={{
            label: blocker.action_label,
            consequence: blocker.consequence,
            href: blocker.action_href,
          }}
        />
      ))}
    </div>
  );
}

function CaseCard({ result }: { result: BusinessCaseResult }) {
  const tone = verdictTone(result.verdict);
  const scenarioUsed = Boolean(result.metadata_json.scenario_used);
  const warnings = stringList(result.route_summary_json.planning_warnings);
  return (
    <article className={`case-card ${tone}`}>
      <div className="case-card-header">
        <div>
          <span className="eyebrow">Business case</span>
          <h2>{result.display_name}</h2>
          <p className="muted">
            Verdict: <strong>{statusLabel(result.verdict)}</strong>
            {scenarioUsed ? " using a shadow route scenario." : ""}
          </p>
        </div>
        <div className="score-bubble">{result.score}</div>
      </div>

      <CaseSignals result={result} />

      <div className="three-column-facts">
        <div>
          <h3>Evidence</h3>
          <p className="muted">{evidenceSummary(result)}</p>
        </div>
        <div>
          <h3>KOF fit</h3>
          <p className="muted">{fitSummary(result)}</p>
        </div>
        <div>
          <h3>Route</h3>
          <p className="muted">{routeSummary(result)}</p>
        </div>
      </div>

      {warnings.length ? (
        <ActionNotice
          explanation={warnings[0]}
          severity="warning"
          title="Planner route action available"
          primaryAction={{
            label: "Review route and KOF slot",
            consequence: "Opens the opportunity workspace where route review and KOF slot actions live.",
            href: "/opportunities",
          }}
        />
      ) : null}

      <BlockerNotices result={result} />

      {result.source_links_json.length ? (
        <details className="source-list">
          <summary>View source evidence links</summary>
          <div className="source-list-items">
            {result.source_links_json.slice(0, 6).map((link) => (
              <a href={link.url} key={`${result.id}-${link.url}`} rel="noreferrer" target="_blank">
                {link.type}: {link.label}
              </a>
            ))}
          </div>
        </details>
      ) : null}
    </article>
  );
}

export default async function BusinessCasesPage() {
  let runs: BusinessCaseRun[];
  try {
    runs = await getBusinessCaseRuns();
  } catch (error) {
    return <ApiOfflineState message={error instanceof Error ? error.message : "Roadshow API is unavailable."} />;
  }

  const latest = runs[0];

  return (
    <div className="stack">
      <section className="hero guided-hero">
        <div className="hero-card guided-start-card">
          <span className="eyebrow">Business Case Audit</span>
          <h1 className="hero-title">Test whether Roadshow earns its place in real seminar work.</h1>
          <p className="hero-copy">
            Run a non-sendable audit across Mirko Wiederholt, Rahul Deb, Daron Acemoglu, and one real-data negative control.
          </p>
        </div>
        <section className="primary-flow-card" data-primary-action="true">
          <span className="eyebrow">Quality gate</span>
          <h2>Run the real-case shadow audit</h2>
          <p>Roadshow evaluates evidence, KOF fit, route logic, first-class fare status, and draft gating without sending anything.</p>
          <BusinessCaseRunButton onCompleteHref="/business-cases" />
        </section>
      </section>

      <section className="guided-metrics" aria-label="Latest business-case audit">
        <div className="metric">
          <div className="metric-value">{metric(latest, "case_count")}</div>
          <div className="metric-label">Cases tested</div>
        </div>
        <div className="metric">
          <div className="metric-value">{metric(latest, "draft_allowed_count")}</div>
          <div className="metric-label">Drafts allowed in shadow</div>
        </div>
        <div className="metric">
          <div className="metric-value">{metric(latest, "blocked_count")}</div>
          <div className="metric-label">Blocked with reasons</div>
        </div>
        <div className="metric">
          <div className="metric-value">{metric(latest, "audit_error_count")}</div>
          <div className="metric-label">Audit errors</div>
        </div>
      </section>

      {!latest ? (
        <Panel title="No audit run yet" copy="Start with the shadow audit to see whether Roadshow can handle the named real cases end to end.">
          <ActionNotice
            explanation="No business-case run has been recorded yet."
            severity="info"
            title="Run the first shadow audit"
            primaryAction={{
              label: "Run shadow business-case audit",
              consequence: "Creates a non-sendable audit result for the named cases.",
            }}
            primaryActionSlot={<BusinessCaseRunButton onCompleteHref="/business-cases" />}
          />
        </Panel>
      ) : (
        <Panel
          title="Latest audit results"
          copy={`Run ${latest.id} finished with status ${latest.status}${latest.finished_at ? ` at ${new Date(latest.finished_at).toLocaleString()}` : ""}.`}
        >
          <div className="case-grid">
            {latest.results.map((result) => (
              <CaseCard key={result.id} result={result} />
            ))}
          </div>
        </Panel>
      )}

      {runs.length > 1 ? (
        <Panel title="Previous runs" copy="Use earlier runs to compare whether source sync, evidence review, or route fixes improved the business case.">
          <div className="guided-list compact">
            {runs.slice(1, 6).map((run) => (
              <article className="guided-item" key={run.id}>
                <span className="status-pill">{run.status}</span>
                <div>
                  <h3>{new Date(run.started_at).toLocaleString()}</h3>
                  <p className="muted">
                    {metric(run, "case_count")} cases, {metric(run, "blocked_count")} blocked, {metric(run, "draft_allowed_count")} draft previews allowed.
                  </p>
                  <Link className="button-link" href={`/business-cases?latest=${run.id}` as Route}>
                    View audit run summary
                  </Link>
                </div>
              </article>
            ))}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
