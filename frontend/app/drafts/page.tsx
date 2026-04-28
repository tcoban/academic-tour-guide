import Link from "next/link";

import { Panel } from "@/components/panel";
import { getDrafts } from "@/lib/api";

export default async function DraftLibraryPage() {
  const drafts = await getDrafts();
  const templates = new Set(drafts.map((draft) => draft.template_label || draft.metadata_json.template_label || "Unknown"));
  const readyDrafts = drafts.filter((draft) => draft.status === "draft").length;

  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Draft Library</span>
          <h1 className="hero-title">Every outreach draft in one place.</h1>
          <p className="hero-copy">
            Browse generated drafts, compare template variants, and jump back into the provenance-backed preview before anything leaves KOF.
          </p>
          <div className="kpi-grid">
            <div className="metric">
              <div className="metric-value">{drafts.length}</div>
              <div className="metric-label">Generated drafts</div>
            </div>
            <div className="metric">
              <div className="metric-value">{readyDrafts}</div>
              <div className="metric-label">Ready draft records</div>
            </div>
            <div className="metric">
              <div className="metric-value">{templates.size}</div>
              <div className="metric-label">Templates used</div>
            </div>
          </div>
        </div>
        <Panel title="Library use" copy="Drafts are generated only after approved hook facts are available.">
          <div className="card-list">
            <div className="list-card">
              <h3>Compare variants</h3>
              <p className="muted">Generate Concierge, Academic Hook, and Cost-share versions from the Opportunities page.</p>
            </div>
            <div className="list-card">
              <h3>Preview before sending</h3>
              <p className="muted">Each draft page includes facts used, checklist, copy, and export actions.</p>
            </div>
          </div>
        </Panel>
      </section>

      <section className="draft-library-grid">
        {drafts.map((draft) => (
          <article className="list-card draft-library-card" key={draft.id}>
            <div className="panel-header">
              <div>
                <h3>{draft.researcher_name}</h3>
                <p className="muted">{draft.researcher_home_institution || "Institution pending"}</p>
              </div>
              <span className="status-pill">{draft.status}</span>
            </div>
            <p className="muted">{draft.subject}</p>
            <div className="timeline-strip">
              <span className="timeline-chip">{draft.template_label || draft.metadata_json.template_label || "Template unknown"}</span>
              <span className="timeline-chip">Score {draft.cluster_score}</span>
              <span className="timeline-chip">
                {draft.cluster_start_date} to {draft.cluster_end_date}
              </span>
            </div>
            <p className="fine-print">Generated {new Date(draft.created_at).toLocaleString()}</p>
            <Link className="ghost-button" href={`/drafts/${draft.id}`}>
              Open draft
            </Link>
          </article>
        ))}
      </section>
    </div>
  );
}
