"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { updateDraftStatus } from "@/lib/api";

const STATUSES = [
  { key: "reviewed", label: "Mark reviewed" },
  { key: "sent_manually", label: "Mark sent" },
  { key: "archived", label: "Archive" },
];

type DraftStatusActionsProps = {
  draftId: string;
  currentStatus: string;
};

export function DraftStatusActions({ draftId, currentStatus }: DraftStatusActionsProps) {
  const router = useRouter();
  const [pendingStatus, setPendingStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function setStatus(nextStatus: string) {
    setPendingStatus(nextStatus);
    setError(null);
    try {
      await updateDraftStatus(draftId, nextStatus);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Status update failed.");
    } finally {
      setPendingStatus(null);
    }
  }

  return (
    <div className="template-actions">
      {STATUSES.map((status) => (
        <button
          className={status.key === "archived" ? "ghost-button" : undefined}
          disabled={pendingStatus !== null || currentStatus === status.key}
          key={status.key}
          onClick={() => setStatus(status.key)}
          type="button"
        >
          {pendingStatus === status.key ? "Updating..." : status.label}
        </button>
      ))}
      {error ? <span className="fine-print">{error}</span> : null}
    </div>
  );
}
