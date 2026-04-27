import { Panel } from "@/components/panel";
import { ReviewInbox } from "@/components/review-inbox";
import { getReviewQueue } from "@/lib/api";

export default async function ReviewPage() {
  const candidates = await getReviewQueue();

  return (
    <div className="stack">
      <Panel
        title="Review Inbox"
        copy="Approve or reject pending biographic evidence before the outreach engine can use it."
      >
        {candidates.length ? (
          <ReviewInbox candidates={candidates} />
        ) : (
          <p className="fine-print">No pending fact candidates are waiting for review.</p>
        )}
      </Panel>
    </div>
  );
}
