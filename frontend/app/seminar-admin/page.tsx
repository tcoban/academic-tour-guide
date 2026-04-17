import { OverrideManager } from "@/components/override-manager";
import { Panel } from "@/components/panel";
import { TemplateManager } from "@/components/template-manager";
import { getCalendarOverlay, getSeminarOverrides, getSeminarTemplates } from "@/lib/api";

export default async function SeminarAdminPage() {
  const [templates, overrides, overlay] = await Promise.all([
    getSeminarTemplates(),
    getSeminarOverrides(),
    getCalendarOverlay(),
  ]);

  return (
    <div className="stack">
      <section className="dual-grid">
        <Panel title="Recurring templates" copy="Seed the weekly KOF seminar rhythm.">
          <TemplateManager templates={templates} />
        </Panel>
        <Panel title="Manual overrides" copy="Explicitly open or block one-off dates.">
          <OverrideManager overrides={overrides} />
        </Panel>
      </section>

      <Panel title="Current overlay snapshot" copy="Occupied KOF events from the public calendar and the derived open windows.">
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

