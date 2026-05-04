import { ActionNotice } from "@/components/action-notice";
import { Panel } from "@/components/panel";

export function ApiOfflineState({ message }: { message?: string }) {
  return (
    <div className="stack">
      <section className="hero single-hero">
        <div className="hero-card">
          <span className="eyebrow">Roadshow API unavailable</span>
          <h1 className="hero-title">Roadshow cannot load live seminar data.</h1>
          <p className="hero-copy">
            Roadshow API is unavailable. Contact the operator or check service status before making seminar decisions.
          </p>
          {message ? (
            <ActionNotice
              severity="error"
              title="API connection failed"
              explanation={message}
              primaryAction={{
                label: "Return to Start",
                consequence: "Keeps you on the main operating surface while the API is restored.",
                href: "/",
              }}
              secondaryActions={[
                {
                  label: "Inspect data sources",
                  consequence: "Opens the source workspace once the API is reachable again.",
                  href: "/source-health",
                },
              ]}
            />
          ) : null}
        </div>
      </section>
      <Panel title="Operational status" copy="This screen is read-only until the API is reachable again.">
        <p className="muted">No source sync, evidence review, calendar overlay, or draft workflow can run while the API is unavailable.</p>
      </Panel>
    </div>
  );
}
