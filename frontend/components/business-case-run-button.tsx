"use client";

import { useState } from "react";

import { PurposeButton } from "@/components/purpose-button";
import { runBusinessCaseAudit, type BusinessCaseRun } from "@/lib/api";

type BusinessCaseRunButtonProps = {
  onCompleteHref?: string;
};

export function BusinessCaseRunButton({ onCompleteHref }: BusinessCaseRunButtonProps) {
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<BusinessCaseRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setPending(true);
    setError(null);
    try {
      const run = await runBusinessCaseAudit();
      setResult(run);
      if (onCompleteHref) {
        window.location.href = `${onCompleteHref}?latest=${run.id}`;
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Business-case audit could not be completed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <PurposeButton
      helperText="Runs Mirko Wiederholt, Rahul Deb, Daron Acemoglu, and a real-data negative control through a non-sendable shadow audit."
      label="Run shadow business-case audit"
      pending={pending}
      resultText={result ? `Audit completed with status ${result.status}.` : null}
      errorText={error}
      runningLabel="Running shadow audit"
      onClick={handleClick}
    />
  );
}
