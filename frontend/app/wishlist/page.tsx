import Link from "next/link";

import { Panel } from "@/components/panel";
import { WishlistManager } from "@/components/wishlist-manager";
import { getInstitutions, getResearchers, getWishlist, getWishlistAlerts } from "@/lib/api";

export default async function WishlistPage() {
  const [institutions, researchers, entries, alerts] = await Promise.all([
    getInstitutions(),
    getResearchers(),
    getWishlist(),
    getWishlistAlerts(),
  ]);
  const kof = institutions.find((institution) => institution.name.includes("KOF")) ?? institutions[0];
  const newAlerts = alerts.filter((alert) => alert.status === "new");

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
              <div className="metric-value">{researchers.length}</div>
              <div className="metric-label">Known speakers</div>
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
                        Speaker dossier
                      </Link>
                    ) : null}
                    <span className="fine-print">{new Date(alert.created_at).toLocaleString()}</span>
                  </div>
                </div>
              ))
            ) : (
              <p className="fine-print">No wishlist alerts yet. Add a speaker or topic, then run Scout ingestion or seed demo data.</p>
            )}
          </div>
        </Panel>
      </section>
    </div>
  );
}
