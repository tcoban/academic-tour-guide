import Link from "next/link";

import { ActionNotice } from "@/components/action-notice";
import { Panel } from "@/components/panel";
import { DismissWishlistMatchButton, RefreshWishlistMatchesButton, TourAssemblyProposalButton } from "@/components/tour-assembly-actions";
import { WishlistAlertActions } from "@/components/wishlist-alert-actions";
import { WishlistManager } from "@/components/wishlist-manager";
import { getInstitutions, getResearchers, getWishlist, getWishlistAlerts, getWishlistMatches } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export default async function WishlistPage() {
  const [institutions, researchers, entries, alerts] = await Promise.all([
    getInstitutions(),
    getResearchers(),
    getWishlist(),
    getWishlistAlerts(),
  ]);
  const matches = await getWishlistMatches();
  const kof = institutions.find((institution) => institution.name.includes("KOF")) ?? institutions[0];
  const newAlerts = alerts.filter((alert) => alert.status === "new");
  const activeMatches = matches.filter((match) => !["dismissed", "stale"].includes(match.status));

  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Roadshow Wishlist</span>
          <h1 className="hero-title">Tell Scout who KOF wants on tour.</h1>
          <p className="hero-copy">
            Wishlist entries turn KOF preferences into alerts when the European seminar trail shows a matching speaker or topic window.
          </p>
          <div className="kpi-grid">
            <div className="metric">
              <div className="metric-value">{entries.length}</div>
              <div className="metric-label">Wishlist entries</div>
            </div>
            <div className="metric">
              <div className="metric-value">{newAlerts.length}</div>
              <div className="metric-label">New Scout alerts</div>
            </div>
            <div className="metric">
              <div className="metric-value">{activeMatches.length}</div>
              <div className="metric-label">Co-host matches</div>
            </div>
          </div>
        </div>
        <Panel title="KOF anchor host" copy="The v1 product remains a KOF-first Roadshow desk.">
          <div className="list-card">
            <h3>{kof?.name ?? "KOF institution pending"}</h3>
            <p className="muted">{[kof?.city, kof?.country].filter(Boolean).join(", ")}</p>
            <p className="fine-print">Marketplace, payments, contracts, and live travel booking remain out-of-scope stubs for this phase.</p>
          </div>
        </Panel>
      </section>

      <Panel
        title="Anonymous co-host matches"
        copy="When two or more nearby institutions wishlist the same speaker, Roadshow can build a masked multi-host tour proposal."
        rightSlot={<RefreshWishlistMatchesButton />}
      >
        <div id="wishlist-matches" />
        <div className="card-list">
          {activeMatches.length ? (
            activeMatches.map((match) => (
              <div className="list-card" key={match.id}>
                <div className="panel-header">
                  <div>
                    <h3>{match.display_speaker_name}</h3>
                    <p className="muted">
                      {match.participant_count} masked hosts within {match.radius_km} km | score {match.score}
                    </p>
                  </div>
                  <span className="status-pill">{match.status}</span>
                </div>
                <div className="timeline-strip">
                  {match.participants.map((participant) => (
                    <span className="timeline-chip" key={participant.id}>
                      {participant.masked_label}: {participant.distance_band}, {participant.budget_status}
                    </span>
                  ))}
                </div>
                <div className="template-actions">
                  <TourAssemblyProposalButton matchGroupId={match.id} />
                  <DismissWishlistMatchButton matchGroupId={match.id} />
                  {match.researcher_id ? (
                    <Link className="ghost-button" href={`/researchers/${match.researcher_id}`}>
                      Inspect speaker evidence
                    </Link>
                  ) : null}
                </div>
              </div>
            ))
          ) : (
            <ActionNotice
              severity="info"
              title="No anonymous co-host match is active"
              explanation="Add the same specific speaker to at least two institution wishlists within 150 km, then refresh matches."
              primaryAction={{
                label: "Refresh anonymous matches",
                consequence: "Rechecks active speaker-specific wishlist entries against the co-host radius rule.",
              }}
              primaryActionSlot={<RefreshWishlistMatchesButton />}
            />
          )}
        </div>
      </Panel>

      <section className="dual-grid">
        <Panel title="Wishlist admin" copy="Add specific speakers or topics that should trigger Roadshow alerts.">
          {kof ? (
            <WishlistManager entries={entries} researchers={researchers} kofInstitutionId={kof.id} />
          ) : (
            <p className="fine-print">No institution record is available yet.</p>
          )}
        </Panel>

        <Panel title="Scout alerts" copy="New matches generated from active wishlist entries and trip clusters.">
          <div className="card-list">
            {alerts.length ? (
              alerts.map((alert) => (
                <div className="list-card" key={alert.id}>
                  <div className="panel-header">
                    <div>
                      <h3>{alert.researcher_name || "Matched speaker"}</h3>
                      <p className="muted">{alert.match_reason}</p>
                    </div>
                    <span className="status-pill">{alert.score}</span>
                  </div>
                  <div className="template-actions">
                    {alert.researcher_id ? (
                      <Link className="ghost-button" href={`/researchers/${alert.researcher_id}`}>
                        Inspect speaker evidence
                      </Link>
                    ) : null}
                    <WishlistAlertActions alertId={alert.id} />
                    <span className="fine-print">{new Date(alert.created_at).toLocaleString()}</span>
                  </div>
                </div>
              ))
            ) : (
              <ActionNotice
                severity="info"
                title="No wishlist alerts yet"
                explanation="Add a speaker or topic, then run real source sync from Start so Scout can detect matching trip windows."
                primaryAction={{
                  label: "Run real source sync",
                  consequence: "Returns to Start where the guided sync updates source data and wishlist alerts.",
                  href: "/",
                }}
              />
            )}
          </div>
        </Panel>
      </section>
    </div>
  );
}
