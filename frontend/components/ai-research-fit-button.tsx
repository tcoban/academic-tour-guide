"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PurposeButton } from "@/components/purpose-button";
import { runAiResearchFit } from "@/lib/api";

export function AiResearchFitButton({ clusterId, className }: { clusterId: string; className?: string }) {
  const router = useRouter();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    try {
      setRunning(true);
      setResult(null);
      setError(null);
      await runAiResearchFit(clusterId);
      setResult("AI research-fit explanation updated. The score did not change.");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "AI research-fit explanation failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <PurposeButton
      className={className}
      errorText={error}
      helperText="Adds a zero-point AI explanation from tenant priorities and existing evidence; deterministic score stays unchanged."
      label="Explain research fit with AI"
      onClick={handleClick}
      pending={running}
      resultText={result}
      runningLabel="Explaining research fit..."
    />
  );
}
