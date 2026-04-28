"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { runBiographerRefresh, runRepecSync, type JobRunResponse } from "@/lib/api";

type ResearcherRefreshActionsProps = {
  researcherId: string;
};

type JobName = "repec" | "biographer";

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
      const summary = job === "repec" ? await runRepecSync(researcherId) : await runBiographerRefresh(researcherId);
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
        <button className="ghost-button" disabled={running !== null} onClick={() => run("repec")} type="button">
          {running === "repec" ? "Syncing RePEc..." : "Sync RePEc identity"}
        </button>
        <button disabled={running !== null} onClick={() => run("biographer")} type="button">
          {running === "biographer" ? "Refreshing..." : "Refresh biographer dossier"}
        </button>
      </div>

      {result ? (
        <div className="job-result">
          <strong>{result.job === "repec" ? "RePEc sync finished" : "Biographer refresh finished"}</strong>
          <span>{jobSummary(result.summary)}</span>
        </div>
      ) : null}

      {error ? <p className="source-error">{error}</p> : null}
    </div>
  );
}
