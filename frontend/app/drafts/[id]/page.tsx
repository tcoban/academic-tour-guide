import Link from "next/link";

import { ActionNotice } from "@/components/action-notice";
import { DraftClipboardActions } from "@/components/draft-clipboard-actions";
import { DraftStatusActions } from "@/components/draft-status-actions";
import { Panel } from "@/components/panel";
import { getDraft } from "@/lib/server-api";

export const dynamic = "force-dynamic";

type DraftPageProps = {
  params: Promise<{ id: string }>;
};

function suggestedEmailBody(body: string): string {
  return body.includes("Suggested email draft:") ? body.split("Suggested email draft:", 2)[1].trim() : body;
}

function displayTemplateLabel(metadata: { template_label?: string; template_key?: string }): string {
  return metadata.template_key === "multi_host_tour" ? metadata.template_label ?? "Multi-host Roadshow tour" : "KOF invitation";
}

export default async function DraftPage({ params }: DraftPageProps) {
  const { id } = await params;
  const draft = await getDraft(id);
  const checklist = draft.metadata_json.checklist ?? [];
  const usedFacts = draft.metadata_json.used_facts ?? [];
  const candidateSlot = draft.metadata_json.candidate_slot;
  const costShare = draft.metadata_json.cost_share;
  const sendBrief = draft.metadata_json.send_brief ?? [];
  const statusHistory = draft.metadata_json.status_history ?? [];
  const emailBody = suggestedEmailBody(draft.body);
  const templateLabel = displayTemplateLabel(draft.metadata_json);

  return (
    <div className="stack">
      <Panel
        title={draft.subject}
        copy={`Generated ${new Date(draft.created_at).toLocaleString()} with ${templateLabel}`}
        rightSlot={<Link className="ghost-button" href="/opportunities">Back to opportunities</Link>}
      >
        <div className="stack">
          <div className="panel-header">
            <span className={`status-pill ${draft.status === "blocked" ? "blocked" : ""}`}>{draft.status}</span>
            <DraftClipboardActions subject={draft.subject} body={emailBody} />
          </div>
          <div id="draft-status-actions">
            <DraftStatusActions checklist={checklist} currentStatus={draft.status} draftId={draft.id} />
          </div>
          {draft.blocked_reason ? (
            <ActionNotice
              severity="blocked"
              title="Draft cannot move forward yet"
              explanation={draft.blocked_reason}
              primaryAction={{
                label: "Approve evidence for outreach",
                consequence: "Opens the evidence queue filtered to this speaker so missing approved facts can be cleared.",
                href: `/review?status=pending&researcher_id=${draft.researcher_id}`,
              }}
              secondaryActions={[
                {
                  label: "Search trusted evidence",
                  consequence: "Opens the speaker dossier where Roadshow can search trusted sources or add an approved fact.",
                  href: `/researchers/${draft.researcher_id}#manual-facts`,
                },
              ]}
            />
          ) : null}
        </div>
      </Panel>

      <Panel title="Suggested email" copy="This is the invitation text to review and send manually outside Roadshow. Internal notes are separated below.">
        <textarea readOnly value={emailBody} />
      </Panel>

      {sendBrief.length > 0 ? (
        <Panel title="Internal send brief" copy="Concise operator notes for turning this draft into a KOF-ready invitation. Do not paste these into the email.">
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
                {item.status === "needs_review" ? (
                  <ActionNotice
                    severity="warning"
                    title={`${item.label} needs confirmation`}
                    explanation="Confirm this checklist item before moving the draft to reviewed."
                    primaryAction={{
                      label: "Confirm draft checklist",
                      consequence: "Jumps to the checklist controls at the top of this draft.",
                      href: "#draft-status-actions",
                    }}
                  />
                ) : null}
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
        <Panel title="Internal logistics note" copy="Screening estimate for KOF planning only; it is not part of the invitation email.">
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
