"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PurposeButton } from "@/components/purpose-button";
import { runEvidenceSearch, runRepecSync, type JobRunResponse } from "@/lib/api";

type ResearcherRefreshActionsProps = {
  researcherId: string;
};

type JobName = "repec" | "evidence";

function jobSummary(result: JobRunResponse): string {
  return `${result.processed_count} processed, ${result.created_count} created, ${result.updated_count} updated`;
}

export function ResearcherRefreshActions({ researcherId }: ResearcherRefreshActionsProps) {
  const router = useRouter();
  const [running, setRunning] = useState<JobName | null>(null);
  const [result, setResult] = useState<{ job: JobName; summary: JobRunResponse } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(job: JobName) {
    try {
      setRunning(job);
      setResult(null);
      setError(null);
      const summary = job === "repec" ? await runRepecSync(researcherId) : await runEvidenceSearch(researcherId);
      setResult({ job, summary });
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Dossier refresh failed.");
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="stack">
      <div className="job-runner">
        <PurposeButton
          className="ghost-button"
          disabledReason={running && running !== "repec" ? "Another dossier refresh is already running." : null}
          errorText={error && running === null ? error : null}
          helperText="Updates ranking and identity metadata before evidence is reviewed."
          label="Sync RePEc identity"
          onClick={() => run("repec")}
          pending={running === "repec"}
          runningLabel="Syncing RePEc..."
        />
        <PurposeButton
          disabledReason={running && running !== "evidence" ? "Another dossier refresh is already running." : null}
          errorText={error && running === null ? error : null}
          helperText="Searches RePEc Genealogy, ORCID, CEPR, institution profiles, and CV links for reviewable facts."
          label="Search trusted evidence"
          onClick={() => run("evidence")}
          pending={running === "evidence"}
          runningLabel="Searching trusted sources..."
        />
      </div>

      {result ? (
        <div className="job-result">
          <strong>{result.job === "repec" ? "RePEc sync finished" : "Evidence search finished"}</strong>
          <span>{jobSummary(result.summary)}</span>
        </div>
      ) : null}
    </div>
  );
}
