import Link from "next/link";

import { ActionNotice } from "@/components/action-notice";
import { DraftStatusActions } from "@/components/draft-status-actions";
import { Panel } from "@/components/panel";
import { getDrafts } from "@/lib/api";

export const dynamic = "force-dynamic";

type DraftLibraryPageProps = {
  searchParams?: Promise<{ status?: string }>;
};

const STATUS_FILTERS = [
  { key: "all", label: "All" },
  { key: "draft", label: "Draft" },
  { key: "reviewed", label: "Reviewed" },
  { key: "sent_manually", label: "Sent manually" },
  { key: "archived", label: "Archived" },
];

function displayTemplateLabel(draft: { template_label?: string | null; metadata_json: { template_label?: string; template_key?: string } }): string {
  return draft.metadata_json.template_key === "multi_host_tour" ? draft.template_label || draft.metadata_json.template_label || "Multi-host Roadshow tour" : "KOF invitation";
}

export default async function DraftLibraryPage({ searchParams }: DraftLibraryPageProps) {
  const params = searchParams ? await searchParams : {};
  const activeStatus = params.status ?? "all";
  const drafts = await getDrafts(activeStatus === "all" ? undefined : activeStatus);
  const normalDrafts = drafts.filter((draft) => (draft.metadata_json.template_key ?? "kof_invitation") !== "multi_host_tour").length;
  const readyDrafts = drafts.filter((draft) => draft.status === "draft").length;

  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Draft Library</span>
          <h1 className="hero-title">Every outreach draft in one place.</h1>
          <p className="hero-copy">
            Browse KOF invitation drafts, review the internal send brief, and jump back into the provenance-backed preview before anything leaves KOF.
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
              <div className="metric-value">{normalDrafts}</div>
              <div className="metric-label">KOF invitations</div>
            </div>
          </div>
        </div>
        <Panel title="Library use" copy="Drafts are generated only after approved hook facts are available.">
          <div className="card-list">
            <div className="list-card">
              <h3>Review one invitation</h3>
              <p className="muted">Each opportunity creates one KOF invitation draft. Angle, evidence, and logistics notes stay internal.</p>
            </div>
            <div className="list-card">
              <h3>Preview before sending</h3>
              <p className="muted">Each draft page separates the email text from the send brief, checklist, and provenance.</p>
            </div>
          </div>
        </Panel>
      </section>

      <Panel title="Filters" copy="Move through the outreach pipeline without losing provenance.">
        <div className="timeline-strip">
          {STATUS_FILTERS.map((filter) => (
            <Link className={`timeline-chip ${activeStatus === filter.key ? "selected-chip" : ""}`} href={filter.key === "all" ? "/drafts" : `/drafts?status=${filter.key}`} key={filter.key}>
              {filter.label}
            </Link>
          ))}
        </div>
      </Panel>

      <section className="draft-library-grid">
        {drafts.length ? drafts.map((draft) => (
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
              <span className="timeline-chip">{displayTemplateLabel(draft)}</span>
              <span className="timeline-chip">Score {draft.cluster_score}</span>
              <span className="timeline-chip">
                {draft.cluster_start_date} to {draft.cluster_end_date}
              </span>
            </div>
            <p className="fine-print">Generated {new Date(draft.created_at).toLocaleString()}</p>
            <div className="template-actions">
              <Link className="ghost-button" href={`/drafts/${draft.id}`}>
                Inspect draft preview
              </Link>
              <DraftStatusActions currentStatus={draft.status} draftId={draft.id} />
            </div>
          </article>
        )) : (
          <ActionNotice
            severity="info"
            title="No drafts in this view"
            explanation="Invitation drafts appear after an opportunity has an approved evidence gate and a concrete KOF slot."
            primaryAction={{
              label: "Inspect opportunity workbench",
              consequence: "Shows which opportunities are draft-ready and which blockers remain.",
              href: "/opportunities",
            }}
            secondaryActions={[
              {
                label: "Approve evidence for outreach",
                consequence: "Opens the evidence queue that most often blocks draft creation.",
                href: "/review?status=pending",
              },
            ]}
          />
        )}
      </section>
    </div>
  );
}
