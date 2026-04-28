import { Panel } from "@/components/panel";
import { SourceJobRunner } from "@/components/source-job-runner";
import { getSourceHealth, getSourceHealthHistory, getSourceReliability } from "@/lib/api";

function sourceLabel(name: string): string {
  return name
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function healthTone(status: string, eventCount: number): string {
  if (status !== "ok") {
    return "blocked";
  }
  if (eventCount === 0) {
    return "warning";
  }
  return "";
}

function trendTone(needsAttention: boolean, trend: string): string {
  if (needsAttention) {
    return "blocked";
  }
  if (trend === "new") {
    return "warning";
  }
  return "";
}

export default async function SourceHealthPage() {
  const [health, history, reliability] = await Promise.all([getSourceHealth(), getSourceHealthHistory(), getSourceReliability()]);
  const totalEvents = health.reduce((sum, source) => sum + source.event_count, 0);
  const healthySources = health.filter((source) => source.status === "ok" && source.event_count > 0).length;
  const zeroEventSources = health.filter((source) => source.status === "ok" && source.event_count === 0).length;
  const failingSources = health.filter((source) => source.status !== "ok").length;
  const latestHistory = history.slice(0, 12);
  const attentionSources = reliability.filter((source) => source.needs_attention);

  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Operational Radar</span>
          <h1 className="hero-title">Know which ears are actually hearing.</h1>
          <p className="hero-copy">
            This live audit fetches each pilot source, runs the parser, and shows whether Roadshow is extracting current events or
            needs adapter attention.
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
              <div className="metric-label">Sources needing attention</div>
            </div>
          </div>
        </div>
        <Panel title="What this means" copy="Zero events can mean either no public events or a source that needs a richer adapter.">
          <div className="card-list">
            <div className="list-card">
              <h3>{failingSources} failing sources</h3>
              <p className="muted">Network, URL, or parser exceptions show up as blocked health cards.</p>
            </div>
            <div className="list-card">
              <h3>KOF host calendar</h3>
              <p className="muted">KOF is now read through the ETH public calendar JSON feed discovered from the event page.</p>
            </div>
          </div>
        </Panel>
      </section>

      <Panel title="Run sync jobs" copy="Trigger the practical maintenance jobs without leaving the dashboard.">
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
                      {source.checks_recorded} checks · {(source.success_rate * 100).toFixed(0)}% success
                    </p>
                  </div>
                  <span className={`status-pill ${trendTone(source.needs_attention, source.trend)}`}>{source.trend}</span>
                </div>
                <div className="timeline-strip">
                  <span className="timeline-chip">latest {source.latest_event_count}</span>
                  <span className="timeline-chip">avg {source.average_event_count}</span>
                  {source.previous_event_count !== null && source.previous_event_count !== undefined ? (
                    <span className="timeline-chip">previous {source.previous_event_count}</span>
                  ) : null}
                </div>
                {source.attention_reason ? <p className="fine-print">{source.attention_reason}</p> : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="fine-print">No reliability analytics yet. Record at least one source audit to start the trend line.</p>
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
          <p className="fine-print">No recorded audits yet. Use “Record source audit” to create the first history row for each source.</p>
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

            {source.error ? <p className="source-error">{source.error}</p> : null}

            {source.samples.length > 0 ? (
              <div className="card-list">
                {source.samples.map((sample) => (
                  <div className="list-card" key={`${source.source_name}-${sample}`}>
                    <p>{sample}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="fine-print">No extractable event samples were found in the current audit.</p>
            )}
          </Panel>
        ))}
      </section>
    </div>
  );
}
