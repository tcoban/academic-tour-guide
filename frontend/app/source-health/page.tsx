import { ActionNotice } from "@/components/action-notice";
import { Panel } from "@/components/panel";
import { SourceJobRunner } from "@/components/source-job-runner";
import { getSourceHealth, getSourceHealthHistory, getSourceReliability } from "@/lib/api";

export const dynamic = "force-dynamic";

function sourceLabel(name: string): string {
  return name
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function healthTone(status: string, eventCount: number): string {
  if (status === "needs_adapter") {
    return "warning";
  }
  if (status !== "ok") {
    return "blocked";
  }
  return "";
}

function trendTone(needsAttention: boolean, trend: string): string {
  if (needsAttention) {
    return "blocked";
  }
  return "";
}

function sourceActionNotice({
  title,
  explanation,
  officialUrl,
  actionLabel,
  actionHref,
  consequence,
  severity = "warning",
}: {
  title: string;
  explanation: string;
  officialUrl?: string | null;
  actionLabel?: string | null;
  actionHref?: string | null;
  consequence?: string | null;
  severity?: "warning" | "blocked" | "error" | "info";
}) {
  const href = actionHref || officialUrl || "#source-operations";
  const external = href.startsWith("http");
  return (
    <ActionNotice
      severity={severity}
      title={title}
      explanation={explanation}
      primaryAction={{
        label: actionLabel || (officialUrl ? "Open official source" : "Run source operations"),
        consequence: consequence || (officialUrl
          ? "Opens the watched institution page so you can confirm whether public future events exist."
          : "Jumps to source operations where you can rerun the audit or source sync."),
        href,
        external,
      }}
      secondaryActions={[
        {
          label: "Run source operations",
          consequence: "Jumps to the controls that rerun KOF sync, external ingest, or source audit.",
          href: "#source-operations",
        },
      ]}
    />
  );
}

export default async function SourceHealthPage() {
  const [health, history, reliability] = await Promise.all([getSourceHealth(), getSourceHealthHistory(), getSourceReliability()]);
  const totalEvents = health.reduce((sum, source) => sum + source.event_count, 0);
  const healthySources = health.filter((source) => source.status === "ok" && source.event_count > 0).length;
  const zeroEventSources = health.filter((source) => source.status === "ok" && source.event_count === 0).length;
  const sourcesWithFetchErrors = health.filter((source) => source.status !== "ok" && source.status !== "needs_adapter").length;
  const latestHistory = history.slice(0, 12);
  const attentionSources = reliability.filter((source) => source.needs_attention);

  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Operational Radar</span>
          <h1 className="hero-title">Know which data sources are actually producing events.</h1>
          <p className="hero-copy">
            This live audit fetches each watched source, runs the parser, and shows whether Roadshow is extracting current events or
            needs source-specific adapter work.
          </p>
          <div className="kpi-grid">
            <div className="metric">
              <div className="metric-value">{healthySources}</div>
              <div className="metric-label">Sources with events</div>
            </div>
            <div className="metric">
              <div className="metric-value">{zeroEventSources}</div>
              <div className="metric-label">Healthy but empty</div>
            </div>
            <div className="metric">
              <div className="metric-value">{totalEvents}</div>
              <div className="metric-label">Events detected now</div>
            </div>
            <div className="metric">
              <div className="metric-value">{attentionSources.length}</div>
              <div className="metric-label">Sources needing action</div>
            </div>
          </div>
        </div>
        <Panel title="What this means" copy="Zero events can mean either no public future events or a source that needs a richer adapter.">
          <div className="card-list">
            <div className="list-card">
              <h3>{sourcesWithFetchErrors} sources with fetch errors</h3>
              <p className="muted">Network, URL, or parser exceptions show up as blocked health cards.</p>
            </div>
            <div className="list-card">
              <h3>KOF host calendar</h3>
              <p className="muted">KOF is now read through the ETH public calendar JSON feed discovered from the event page.</p>
            </div>
          </div>
        </Panel>
      </section>

      <Panel title="Run source operations" copy="Trigger focused maintenance operations without leaving this workspace.">
        <div id="source-operations" />
        <SourceJobRunner />
      </Panel>

      <Panel title="Reliability analytics" copy="Trend signals come from persisted audit history, not only the live snapshot.">
        {reliability.length > 0 ? (
          <div className="history-grid">
            {reliability.map((source) => (
              <div className="list-card" key={source.source_name}>
                <div className="panel-header">
                  <div>
                    <h3>{sourceLabel(source.source_name)}</h3>
                    <p className="muted">
                      {source.checks_recorded} checks | {(source.success_rate * 100).toFixed(0)}% success
                    </p>
                  </div>
                  <span className={`status-pill ${trendTone(source.needs_attention, source.trend)}`}>{source.trend}</span>
                </div>
                <div className="timeline-strip">
                  <span className="timeline-chip">latest {source.latest_event_count}</span>
                  <span className="timeline-chip">last {source.last_event_count}</span>
                  <span className="timeline-chip">avg {source.average_event_count}</span>
                  {source.previous_event_count !== null && source.previous_event_count !== undefined ? (
                    <span className="timeline-chip">previous {source.previous_event_count}</span>
                  ) : null}
                </div>
                {source.needs_attention || source.needs_adapter || source.latest_event_count === 0 ? (
                  sourceActionNotice({
                    title: source.needs_adapter
                      ? "Adapter work is needed for this source"
                      : source.needs_attention
                        ? "Source signal needs action"
                        : "No future events were extracted",
                    explanation:
                      source.attention_reason ||
                      source.latest_error ||
                      "Roadshow did not extract future events from the latest check; confirm the official source or rerun source operations.",
                    officialUrl: source.official_url,
                    actionLabel: source.action_label,
                    actionHref: source.action_href,
                    consequence: source.consequence,
                    severity: source.needs_attention ? "blocked" : "warning",
                  })
                ) : source.official_url ? (
                  <a className="fine-print" href={source.official_url} rel="noreferrer" target="_blank">
                    Official source
                  </a>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <ActionNotice
            severity="info"
            title="No reliability analytics yet"
            explanation="Roadshow needs at least one recorded source audit before it can show trend lines."
            primaryAction={{
              label: "Run source operations",
              consequence: "Jumps to the controls that record the first data-source status check.",
              href: "#source-operations",
            }}
          />
        )}
      </Panel>

      <Panel title="Recorded audit history" copy="Recent persisted checks let us spot source degradation instead of relying on one live snapshot.">
        {latestHistory.length > 0 ? (
          <div className="history-grid">
            {latestHistory.map((record) => (
              <div className="list-card" key={record.id}>
                <div className="panel-header">
                  <div>
                    <h3>{sourceLabel(record.source_name)}</h3>
                    <p className="muted">{new Date(record.checked_at).toLocaleString()}</p>
                  </div>
                  <span className={`status-pill ${healthTone(record.status, record.event_count)}`}>{record.status}</span>
                </div>
                <div className="timeline-strip">
                  <span className="timeline-chip">{record.page_count} pages</span>
                  <span className="timeline-chip">{record.event_count} events</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <ActionNotice
            severity="info"
            title="No recorded audits yet"
            explanation="Use the source operations controls to create the first audit row for each watched source."
            primaryAction={{
              label: "Run source operations",
              consequence: "Jumps to the controls that record data-source status.",
              href: "#source-operations",
            }}
          />
        )}
      </Panel>

      <section className="content-grid">
        {health.map((source) => (
          <Panel
            key={source.source_name}
            title={sourceLabel(source.source_name)}
            copy={`${source.source_type.split("_").join(" ")} checked at ${new Date(source.checked_at).toLocaleString()}`}
          >
            <div className="panel-header">
              <div className="timeline-strip">
                <span className={`status-pill ${healthTone(source.status, source.event_count)}`}>{source.status}</span>
                <span className="timeline-chip">{source.page_count} pages</span>
                <span className="timeline-chip">{source.event_count} events</span>
              </div>
            </div>

            {source.error
              ? sourceActionNotice({
                  title: "Source fetch failed",
                  explanation: source.error,
                  officialUrl: source.official_url,
                  actionLabel: source.action_label,
                  actionHref: source.action_href,
                  consequence: source.consequence,
                  severity: "error",
                })
              : null}

            {source.samples.length > 0 ? (
              <div className="card-list">
                {source.samples.map((sample) => (
                  <div className="list-card" key={`${source.source_name}-${sample}`}>
                    <p>{sample}</p>
                  </div>
                ))}
              </div>
            ) : (
              sourceActionNotice({
                title: source.needs_adapter ? "Extractor not production-ready" : "No event samples found",
                explanation: source.needs_adapter
                  ? "Official source is tracked, but Roadshow still needs a source-specific extractor before events can be ranked."
                  : "No extractable event samples were found in the current audit; confirm the official page or rerun source operations.",
                officialUrl: source.official_url,
                actionLabel: source.action_label,
                actionHref: source.action_href,
                consequence: source.consequence,
                severity: source.needs_adapter ? "warning" : "info",
              })
            )}
          </Panel>
        ))}
      </section>
    </div>
  );
}
