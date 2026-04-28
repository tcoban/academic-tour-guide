import Link from "next/link";

import { DraftClipboardActions } from "@/components/draft-clipboard-actions";
import { DraftStatusActions } from "@/components/draft-status-actions";
import { Panel } from "@/components/panel";
import { getDraft } from "@/lib/api";

type DraftPageProps = {
  params: Promise<{ id: string }>;
};

export default async function DraftPage({ params }: DraftPageProps) {
  const { id } = await params;
  const draft = await getDraft(id);
  const checklist = draft.metadata_json.checklist ?? [];
  const usedFacts = draft.metadata_json.used_facts ?? [];
  const candidateSlot = draft.metadata_json.candidate_slot;
  const costShare = draft.metadata_json.cost_share;
  const sendBrief = draft.metadata_json.send_brief ?? [];
  const statusHistory = draft.metadata_json.status_history ?? [];

  return (
    <div className="stack">
      <Panel
        title={draft.subject}
        copy={`Generated ${new Date(draft.created_at).toLocaleString()} with ${draft.metadata_json.template_label ?? "Outreach template"}`}
        rightSlot={<Link className="ghost-button" href="/opportunities">Back to opportunities</Link>}
      >
        <div className="stack">
          <div className="panel-header">
            <span className={`status-pill ${draft.status === "blocked" ? "blocked" : ""}`}>{draft.status}</span>
            <DraftClipboardActions subject={draft.subject} body={draft.body} />
          </div>
          <DraftStatusActions currentStatus={draft.status} draftId={draft.id} />
          {draft.blocked_reason ? <p className="fine-print">{draft.blocked_reason}</p> : null}
          <textarea readOnly value={draft.body} />
        </div>
      </Panel>

      {sendBrief.length > 0 ? (
        <Panel title="Admin send brief" copy="Concise operator notes for turning this draft into a KOF-ready invitation.">
          <div className="card-list">
            {sendBrief.map((item) => (
              <div className="list-card" key={item.label}>
                <h3>{item.label}</h3>
                <p className="fine-print">{item.detail}</p>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      <section className="dual-grid">
        <Panel title="Approved facts used" copy="Only approved evidence can power the biographic hook.">
          <div className="card-list">
            {usedFacts.map((fact) => (
              <div className="list-card" key={fact.id}>
                <div className="panel-header">
                  <div>
                    <h3>{fact.fact_type}</h3>
                    <p className="muted">{fact.value}</p>
                  </div>
                  <span className="status-pill">{Math.round(fact.confidence * 100)}%</span>
                </div>
                {fact.evidence_snippet ? <p className="fine-print">{fact.evidence_snippet}</p> : null}
                {fact.source_url ? (
                  <a className="fine-print" href={fact.source_url}>
                    Evidence source
                  </a>
                ) : null}
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Invitation checklist" copy="Final human checks before this leaves KOF.">
          <div className="card-list">
            {checklist.map((item) => (
              <div className="list-card" key={item.label}>
                <div className="panel-header">
                  <h3>{item.label}</h3>
                  <span className={`status-pill ${item.status === "needs_review" ? "warning" : ""}`}>{item.status}</span>
                </div>
                <p className="fine-print">{item.detail}</p>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      {candidateSlot ? (
        <Panel title="Candidate KOF slot" copy="Slot proposed by the workbench at draft time.">
          <div className="list-card">
            <h3>{new Date(candidateSlot.starts_at).toLocaleString()}</h3>
            <p className="muted">Until {new Date(candidateSlot.ends_at).toLocaleString()}</p>
            <p className="fine-print">{candidateSlot.source}</p>
          </div>
        </Panel>
      ) : null}

      {costShare ? (
        <Panel title="Cost-sharing estimate" copy="Screening estimate comparing standalone Zurich travel with a Zurich add-on.">
          <div className="list-card">
            <div className="panel-header">
              <div>
                <h3>
                  CHF {costShare.multi_city_incremental_chf} add-on vs CHF {costShare.baseline_round_trip_chf} standalone
                </h3>
                <p className="muted">
                  {costShare.nearest_itinerary_city} is the nearest known stop ({costShare.nearest_distance_km} km,{" "}
                  {costShare.recommended_mode}).
                </p>
              </div>
              <span className="status-pill">{costShare.recommendation}</span>
            </div>
            <div className="timeline-strip">
              <span className="timeline-chip">Savings CHF {costShare.estimated_savings_chf}</span>
              <span className="timeline-chip">ROI {costShare.roi_percent}%</span>
            </div>
            {costShare.assumption_notes.map((note) => (
              <p className="fine-print" key={note}>
                {note}
              </p>
            ))}
          </div>
        </Panel>
      ) : null}

      {statusHistory.length > 0 ? (
        <Panel title="Status history" copy="Lifecycle changes are preserved in draft metadata.">
          <div className="card-list">
            {statusHistory.map((entry) => (
              <div className="list-card" key={`${entry.changed_at}-${entry.to}`}>
                <div className="panel-header">
                  <h3>
                    {entry.from} to {entry.to}
                  </h3>
                  <span className="status-pill">{new Date(entry.changed_at).toLocaleString()}</span>
                </div>
                {entry.note ? <p className="fine-print">{entry.note}</p> : null}
              </div>
            ))}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
