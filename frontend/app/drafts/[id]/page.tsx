import Link from "next/link";

import { Panel } from "@/components/panel";
import { getDraft } from "@/lib/api";

type DraftPageProps = {
  params: Promise<{ id: string }>;
};

export default async function DraftPage({ params }: DraftPageProps) {
  const { id } = await params;
  const draft = await getDraft(id);

  return (
    <Panel
      title={draft.subject}
      copy={`Generated ${new Date(draft.created_at).toLocaleString()}`}
      rightSlot={<Link className="ghost-button" href="/">Back to dashboard</Link>}
    >
      <div className="stack">
        <span className={`status-pill ${draft.status === "blocked" ? "blocked" : ""}`}>{draft.status}</span>
        {draft.blocked_reason ? <p className="fine-print">{draft.blocked_reason}</p> : null}
        <textarea readOnly value={draft.body} />
      </div>
    </Panel>
  );
}
