import Link from "next/link";

import { ActionNotice } from "@/components/action-notice";
import { MorningSweepButton } from "@/components/morning-sweep-button";
import { Panel } from "@/components/panel";
import { getCalendarOverlay, getOpportunityWorkbench, type HostCalendarEvent, type OpenSeminarWindow, type OpportunityCard } from "@/lib/api";

export const dynamic = "force-dynamic";

type CalendarDay = {
  key: string;
  label: string;
  weekday: string;
  hostEvents: HostCalendarEvent[];
  openWindows: OpenSeminarWindow[];
  opportunities: OpportunityCard[];
};

function dateKey(value: string): string {
  return value.slice(0, 10);
}

function addDays(key: string, days: number): string {
  const date = new Date(`${key}T12:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateLabel(key: string): string {
  return new Date(`${key}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" });
}

function formatWeekday(key: string): string {
  return new Date(`${key}T12:00:00`).toLocaleDateString([], { weekday: "short" });
}

function CalendarLoadError({ message }: { message: string }) {
  return (
    <div className="stack">
      <section className="hero single-hero">
        <div className="hero-card">
          <span className="eyebrow">Calendar needs attention</span>
          <h1 className="hero-title">Roadshow could not load the calendar overlay.</h1>
          <p className="hero-copy">
            Page loads are read-only now, so this usually means the API returned an operational error rather than a rebuild problem.
            Run real source sync from Start, then reload the calendar.
          </p>
          <ActionNotice
            severity="error"
            title="Calendar overlay failed"
            explanation={message}
            primaryAction={{
              label: "Run real source sync",
              consequence: "Rebuilds availability through the explicit operations path, then the calendar can be reloaded.",
            }}
            primaryActionSlot={
              <MorningSweepButton helperText="Rebuilds availability through the explicit operations path, then the calendar can be reloaded." />
            }
            secondaryActions={[
              {
                label: "Inspect KOF slot templates",
                consequence: "Opens the settings page where missing or conflicting slot templates can be corrected.",
                href: "/seminar-admin",
              },
            ]}
          />
        </div>
      </section>
      <Panel title="Safe next step" copy="Real source sync rebuilds availability through the explicit operations path.">
        <div className="template-actions">
          <Link className="ghost-button" href="/">
            Return to Start
          </Link>
          <Link className="ghost-button" href="/seminar-admin">
            Inspect slot templates
          </Link>
        </div>
      </Panel>
    </div>
  );
}

function buildCalendarDays(
  hostEvents: HostCalendarEvent[],
  openWindows: OpenSeminarWindow[],
  opportunities: OpportunityCard[],
): CalendarDay[] {
  const interestingDates = [
    ...hostEvents.map((event) => dateKey(event.starts_at)),
    ...openWindows.map((window) => dateKey(window.starts_at)),
    ...opportunities.flatMap((opportunity) => (opportunity.best_window ? [dateKey(opportunity.best_window.starts_at)] : [])),
  ].sort();
  const today = new Date().toISOString().slice(0, 10);
  const startKey = interestingDates.find((key) => key >= today) ?? interestingDates[0] ?? today;
  const windowByDate = new Map<string, OpenSeminarWindow[]>();
  const hostByDate = new Map<string, HostCalendarEvent[]>();
  const opportunityByDate = new Map<string, OpportunityCard[]>();

  for (const window of openWindows) {
    const key = dateKey(window.starts_at);
    windowByDate.set(key, [...(windowByDate.get(key) ?? []), window]);
  }
  for (const event of hostEvents) {
    const key = dateKey(event.starts_at);
    hostByDate.set(key, [...(hostByDate.get(key) ?? []), event]);
  }
  for (const opportunity of opportunities) {
    if (!opportunity.best_window) {
      continue;
    }
    const key = dateKey(opportunity.best_window.starts_at);
    opportunityByDate.set(key, [...(opportunityByDate.get(key) ?? []), opportunity]);
  }

  return Array.from({ length: 42 }, (_, index) => {
    const key = addDays(startKey, index);
    return {
      key,
      label: formatDateLabel(key),
      weekday: formatWeekday(key),
      hostEvents: hostByDate.get(key) ?? [],
      openWindows: windowByDate.get(key) ?? [],
      opportunities: opportunityByDate.get(key) ?? [],
    };
  });
}

export default async function CalendarPage() {
  let overlay: Awaited<ReturnType<typeof getCalendarOverlay>>;
  let workbench: Awaited<ReturnType<typeof getOpportunityWorkbench>>;
  try {
    [overlay, workbench] = await Promise.all([getCalendarOverlay(), getOpportunityWorkbench()]);
  } catch (error) {
    return <CalendarLoadError message={error instanceof Error ? error.message : "Calendar overlay failed to load."} />;
  }
  const calendarDays = buildCalendarDays(overlay.host_events, overlay.open_windows, workbench.opportunities);
  const now = Date.now();
  const futureOpenWindows = overlay.open_windows.filter((window) => new Date(window.starts_at).getTime() >= now);
  const scoringSlotFits = workbench.opportunities.filter((opportunity) => opportunity.best_window?.within_scoring_window).length;
  const draftReadyWithSlot = workbench.opportunities.filter((opportunity) => opportunity.draft_ready && opportunity.best_window).length;
  const nextOpenWindow = futureOpenWindows[0] ?? overlay.open_windows[0];

  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Golden Window Calendar</span>
          <h1 className="hero-title">See availability, pressure, and invite fit together.</h1>
          <p className="hero-copy">
            This board overlays KOF occupied events, derived open seminar windows, and the best matched trip-cluster candidates so admins can
            spot invitation windows without mentally joining three screens.
          </p>
          <div className="kpi-grid">
            <div className="metric">
              <div className="metric-value">{futureOpenWindows.length}</div>
              <div className="metric-label">Future KOF windows</div>
            </div>
            <div className="metric">
              <div className="metric-value">{overlay.host_events.length}</div>
              <div className="metric-label">Occupied host events</div>
            </div>
            <div className="metric">
              <div className="metric-value">{scoringSlotFits}</div>
              <div className="metric-label">Opportunities with slot fit</div>
            </div>
            <div className="metric">
              <div className="metric-value">{draftReadyWithSlot}</div>
              <div className="metric-label">Draft-ready with slot</div>
            </div>
          </div>
        </div>
        <Panel title="How to read it" copy="Green is open capacity, rust is occupied KOF time, gold is an opportunity match.">
          <div className="card-list">
            <div className="list-card">
              <h3>{nextOpenWindow ? new Date(nextOpenWindow.starts_at).toLocaleString() : "No open slots"}</h3>
              <p className="muted">Next derived KOF seminar window.</p>
            </div>
            {!nextOpenWindow ? (
              <ActionNotice
                severity="blocked"
                title="No open KOF windows"
                explanation="The calendar cannot surface invitation dates until a recurring slot or manual opening produces capacity."
                primaryAction={{
                  label: "Set weekly KOF slot",
                  consequence: "Opens KOF slot settings so you can create the recurring seminar pattern.",
                  href: "/seminar-admin",
                }}
                secondaryActions={[
                  {
                    label: "Run real source sync",
                    consequence: "Refreshes KOF occupied events and rebuilds derived availability.",
                    href: "/",
                  },
                ]}
              />
            ) : null}
            <div className="template-actions">
              <Link className="ghost-button" href="/seminar-admin">
                Manage KOF slot templates
              </Link>
              <Link className="ghost-button" href="/opportunities">
                Inspect matched opportunities
              </Link>
            </div>
          </div>
        </Panel>
      </section>

      <Panel title="Six-week overlay" copy="Open windows are generated from templates minus occupied KOF events and manual blocks.">
        <div className="calendar-grid">
          {calendarDays.map((day) => (
            <article className="calendar-day" key={day.key}>
              <div className="calendar-day-heading">
                <span>{day.weekday}</span>
                <strong>{day.label}</strong>
              </div>

              <div className="calendar-items">
                {day.hostEvents.map((event) => (
                  <a className="calendar-chip occupied" href={event.url} key={event.id} rel="noreferrer" target="_blank">
                    <strong>{formatTime(event.starts_at)}</strong>
                    <span>{event.title}</span>
                  </a>
                ))}

                {day.openWindows.map((window) => (
                  <div className="calendar-chip open" key={window.id}>
                    <strong>{formatTime(window.starts_at)}</strong>
                    <span>{String(window.metadata_json.label ?? window.metadata_json.reason ?? "Open KOF window")}</span>
                  </div>
                ))}

                {day.opportunities.slice(0, 3).map((opportunity) => (
                  <Link className="calendar-chip opportunity" href="/opportunities" key={`${day.key}-${opportunity.cluster.id}`}>
                    <strong>{opportunity.researcher.name}</strong>
                    <span>
                      Score {opportunity.cluster.opportunity_score}
                      {opportunity.best_window?.within_scoring_window ? " | slot fit" : " | nearby"}
                    </span>
                  </Link>
                ))}

                {day.opportunities.length > 3 ? (
                  <Link className="calendar-chip more" href="/opportunities">
                    +{day.opportunities.length - 3} more candidate{day.opportunities.length - 3 === 1 ? "" : "s"}
                  </Link>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      </Panel>
    </div>
  );
}
