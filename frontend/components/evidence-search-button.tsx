"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PurposeButton } from "@/components/purpose-button";
import { runEvidenceSearch, type JobRunResponse } from "@/lib/api";

type EvidenceSearchButtonProps = {
  researcherId?: string;
  label?: string;
  className?: string;
  helperText?: string;
};

function summaryText(result: JobRunResponse): string {
  return `${result.processed_count} processed, ${result.created_count} created, ${result.updated_count} updated`;
}

export function EvidenceSearchButton({
  researcherId,
  label = "Search trusted evidence",
  className,
  helperText,
}: EvidenceSearchButtonProps) {
  const router = useRouter();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<JobRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    try {
      setRunning(true);
      setResult(null);
      setError(null);
      const summary = await runEvidenceSearch(researcherId);
      setResult(summary);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Evidence search failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <PurposeButton
      className={className}
      errorText={error}
      helperText={helperText ?? "Searches trusted public sources and places fact candidates in the review queue."}
      label={label}
      onClick={handleClick}
      pending={running}
      resultText={result ? `Evidence search finished: ${summaryText(result)}.` : null}
      runningLabel="Searching trusted sources..."
    />
  );
}
