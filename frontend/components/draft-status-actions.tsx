"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { updateDraftStatus } from "@/lib/api";

type ChecklistItem = {
  label: string;
  status: string;
  detail: string;
};

type DraftStatusActionsProps = {
  draftId: string;
  currentStatus: string;
  checklist?: ChecklistItem[];
};

export function DraftStatusActions({ draftId, currentStatus, checklist = [] }: DraftStatusActionsProps) {
  const router = useRouter();
  const reviewItems = checklist.filter((item) => item.status === "needs_review");
  const [pendingStatus, setPendingStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [confirmedLabels, setConfirmedLabels] = useState<string[]>([]);
  const [sendConfirmed, setSendConfirmed] = useState(false);

  function toggleConfirmation(label: string) {
    setConfirmedLabels((current) => (current.includes(label) ? current.filter((item) => item !== label) : [...current, label]));
  }

  async function setStatus(nextStatus: string) {
    setPendingStatus(nextStatus);
    setError(null);
    try {
      await updateDraftStatus(draftId, nextStatus, {
        note: note || undefined,
        checklist_confirmations: nextStatus === "reviewed" ? confirmedLabels : [],
        send_confirmed: nextStatus === "sent_manually" ? sendConfirmed : false,
      });
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Status update failed.");
    } finally {
      setPendingStatus(null);
    }
  }

  const canReview = checklist.length > 0 && reviewItems.every((item) => confirmedLabels.includes(item.label));
  const canSend = currentStatus === "reviewed" && sendConfirmed;

  return (
    <div className="stack">
      {reviewItems.length > 0 ? (
        <div className="list-card">
          <h3>Checklist confirmations</h3>
          <div className="stack">
            {reviewItems.map((item) => (
              <label className="inline-check" key={item.label}>
                <input
                  checked={confirmedLabels.includes(item.label)}
                  onChange={() => toggleConfirmation(item.label)}
                  type="checkbox"
                />
                {item.label}
              </label>
            ))}
          </div>
        </div>
      ) : null}

      {currentStatus === "reviewed" ? (
        <label className="inline-check">
          <input checked={sendConfirmed} onChange={(event) => setSendConfirmed(event.target.checked)} type="checkbox" />
          I confirm this draft was sent manually outside Roadshow.
        </label>
      ) : null}

      <label>
        Status note
        <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Optional lifecycle note" />
      </label>

      <div className="template-actions">
        <button disabled={pendingStatus !== null || currentStatus === "reviewed" || !canReview} onClick={() => setStatus("reviewed")} type="button">
          {pendingStatus === "reviewed" ? "Confirming review..." : "Confirm draft reviewed"}
        </button>
        <button disabled={pendingStatus !== null || currentStatus === "sent_manually" || !canSend} onClick={() => setStatus("sent_manually")} type="button">
          {pendingStatus === "sent_manually" ? "Recording send..." : "Mark draft sent outside Roadshow"}
        </button>
        <button
          className="ghost-button"
          disabled={pendingStatus !== null || currentStatus === "archived"}
          onClick={() => setStatus("archived")}
          type="button"
        >
          {pendingStatus === "archived" ? "Archiving..." : "Archive draft record"}
        </button>
      </div>

      {checklist.length === 0 ? <span className="fine-print">Open the draft preview to complete checklist-gated review.</span> : null}
      {error ? <span className="fine-print">{error}</span> : null}
    </div>
  );
}
