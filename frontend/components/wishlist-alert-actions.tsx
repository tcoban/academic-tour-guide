"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { updateWishlistAlertStatus } from "@/lib/api";
import { PurposeButton } from "@/components/purpose-button";

export function WishlistAlertActions({ alertId }: { alertId: string }) {
  const router = useRouter();
  const [pendingStatus, setPendingStatus] = useState<string | null>(null);
  const [message, setMessage] = useState<{ status: string; text: string } | null>(null);

  async function update(status: string, note: string) {
    setPendingStatus(status);
    setMessage(null);
    try {
      await updateWishlistAlertStatus(alertId, status, note);
      setMessage({ status, text: status === "dismissed" ? "Alert dismissed." : "Alert marked reviewed." });
      router.refresh();
    } catch (cause) {
      setMessage({ status, text: cause instanceof Error ? cause.message : "Alert update failed." });
    } finally {
      setPendingStatus(null);
    }
  }

  return (
    <div className="template-actions">
      <PurposeButton
        className="ghost-button"
        helperText="Keeps the match visible but removes it from the urgent triage queue."
        label="Mark match reviewed"
        onClick={() => update("reviewed", "Reviewed from the wishlist page.")}
        pending={pendingStatus === "reviewed"}
        resultText={message?.status === "reviewed" && pendingStatus === null ? message.text : null}
        runningLabel="Marking reviewed..."
      />
      <PurposeButton
        className="ghost-button"
        helperText="Dismisses this match when it is not useful for KOF right now."
        label="Dismiss wishlist match"
        onClick={() => update("dismissed", "Dismissed from the wishlist page.")}
        pending={pendingStatus === "dismissed"}
        resultText={message?.status === "dismissed" && pendingStatus === null ? message.text : null}
        runningLabel="Dismissing match..."
      />
    </div>
  );
}
