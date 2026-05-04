"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { runRealSync, type MorningSweepResponse } from "@/lib/api";
import { ACTION_LABELS } from "@/lib/action-labels";
import { PurposeButton } from "@/components/purpose-button";

function summarize(result: MorningSweepResponse): string {
  const failed = result.summary_metrics.failed_steps ?? 0;
  const created = result.summary_metrics.created_count ?? 0;
  const updated = result.summary_metrics.updated_count ?? 0;
  if (failed) {
    return `${failed} step${failed === 1 ? "" : "s"} need attention. Created ${created}, updated ${updated}.`;
  }
  return `Source sync complete. Created ${created}, updated ${updated}.`;
}

export function MorningSweepButton({
  className,
  helperText = "Checks watched sources, syncs KOF, refreshes evidence, rebuilds windows, scores opportunities, and updates alerts.",
  label = ACTION_LABELS.runRealSync,
}: {
  className?: string;
  helperText?: string;
  label?: string;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<MorningSweepResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setPending(true);
    setResult(null);
    setError(null);
    try {
      const response = await runRealSync();
      setResult(response);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Source sync failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <PurposeButton
      className={className}
      errorText={error}
      helperText={helperText}
      label={label}
      onClick={handleClick}
      pending={pending}
      resultText={result ? summarize(result) : null}
      runningLabel="Running source sync..."
    />
  );
}
