"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PurposeButton } from "@/components/purpose-button";
import { runAiEvidenceSearch, type JobRunResponse } from "@/lib/api";

function summaryText(result: JobRunResponse): string {
  return `${result.processed_count} documents checked, ${result.created_count} AI candidates created, ${result.updated_count} updated.`;
}

export function AiEvidenceButton({
  researcherId,
  className,
  label = "Suggest evidence from stored documents",
}: {
  researcherId?: string;
  className?: string;
  label?: string;
}) {
  const router = useRouter();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<JobRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    try {
      setRunning(true);
      setResult(null);
      setError(null);
      const response = await runAiEvidenceSearch(researcherId);
      setResult(response);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "AI evidence suggestion failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <PurposeButton
      className={className}
      errorText={error}
      helperText="Asks Roadshow AI to read already stored source/CV text and create pending evidence candidates only."
      label={label}
      onClick={handleClick}
      pending={running}
      resultText={result ? summaryText(result) : null}
      runningLabel="Suggesting evidence..."
    />
  );
}
