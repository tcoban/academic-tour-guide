import Link from "next/link";

import { ActionNotice } from "@/components/action-notice";
import { MorningSweepButton } from "@/components/morning-sweep-button";
import { OverrideManager } from "@/components/override-manager";
import { Panel } from "@/components/panel";
import { TemplateManager } from "@/components/template-manager";
import { getCalendarOverlay, getSeminarOverrides, getSeminarTemplates } from "@/lib/server-api";

export const dynamic = "force-dynamic";

function SeminarAdminLoadError({ message }: { message: string }) {
  return (
    <div className="stack">
      <section className="hero single-hero">
        <div className="hero-card">
          <span className="eyebrow">KOF slots need attention</span>
          <h1 className="hero-title">Roadshow could not load KOF slot data.</h1>
          <p className="hero-copy">
            The KOF slots page reads the calendar overlay without rebuilding it. Use real source sync for a controlled rebuild, or check
            Roadshow API status if this message persists.
          </p>
          <ActionNotice
            severity="error"
            title="KOF slot data failed to load"
            explanation={message}
            primaryAction={{
              label: "Run real source sync",
              consequence: "Refreshes KOF occupied events and rebuilds open seminar windows through the explicit operations path.",
            }}
            primaryActionSlot={
              <MorningSweepButton helperText="Refreshes KOF occupied events and rebuilds open seminar windows through the explicit operations path." />
            }
            secondaryActions={[
              {
                label: "Return to Start",
                consequence: "Opens the guided operating surface while the API or calendar issue is resolved.",
                href: "/",
              },
            ]}
          />
        </div>
      </section>
      <Panel title="Safe next step" copy="Avoid hidden page-load rebuilds; use explicit operations instead.">
        <Link className="ghost-button" href="/">
          Return to Start
        </Link>
      </Panel>
    </div>
  );
}

export default async function SeminarAdminPage() {
  let templates: Awaited<ReturnType<typeof getSeminarTemplates>>;
  let overrides: Awaited<ReturnType<typeof getSeminarOverrides>>;
  let overlay: Awaited<ReturnType<typeof getCalendarOverlay>>;
  try {
    [templates, overrides, overlay] = await Promise.all([
      getSeminarTemplates(),
      getSeminarOverrides(),
      getCalendarOverlay(),
    ]);
  } catch (error) {
    return <SeminarAdminLoadError message={error instanceof Error ? error.message : "KOF slot data failed to load."} />;
  }

  return (
    <div className="stack">
      <section className="dual-grid">
        <Panel title="Recurring templates" copy="Seed the weekly KOF seminar rhythm.">
          {!templates.length ? (
            <ActionNotice
              severity="blocked"
              title="No weekly KOF slot exists"
              explanation="Opportunity matching cannot produce a concrete invitation date until KOF's recurring seminar pattern is defined."
              primaryAction={{
                label: "Set weekly KOF slot below",
                consequence: "Use the template form in this panel to create the recurring seminar capacity.",
                href: "#template-manager",
              }}
            />
          ) : null}
          <div id="template-manager">
            <TemplateManager templates={templates} />
          </div>
        </Panel>
        <Panel title="Manual overrides" copy="Explicitly open or block one-off dates.">
          <div id="override-manager">
            <OverrideManager overrides={overrides} />
          </div>
        </Panel>
      </section>

      <Panel title="Current overlay snapshot" copy="Occupied KOF events from the public calendar and the derived open windows.">
        {!overlay.open_windows.length ? (
          <ActionNotice
            severity="warning"
            title="No open windows were derived"
            explanation="Either no active template exists, KOF occupied events cover the templates, or manual overrides block the current range."
            primaryAction={{
              label: "Set weekly KOF slot",
              consequence: "Use the recurring template form to create or adjust seminar capacity.",
              href: "#template-manager",
            }}
            secondaryActions={[
              {
                label: "Add manual opening",
                consequence: "Use the override form to reopen a specific KOF seminar date.",
                href: "#override-manager",
              },
            ]}
          />
        ) : null}
        <section className="dual-grid">
          <div className="card-list">
            {overlay.host_events.map((event) => (
              <div className="list-card" key={event.id}>
                <h3>{event.title}</h3>
                <p className="muted">{event.location || "KOF"}</p>
                <p className="fine-print">{new Date(event.starts_at).toLocaleString()}</p>
              </div>
            ))}
          </div>
          <div className="card-list">
            {overlay.open_windows.map((window) => (
              <div className="list-card" key={window.id}>
                <div className="panel-header">
                  <h3>{new Date(window.starts_at).toLocaleString()}</h3>
                  <span className="status-pill">{window.source}</span>
                </div>
                <p className="fine-print">Until {new Date(window.ends_at).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </section>
      </Panel>
    </div>
  );
}
