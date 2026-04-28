"use client";

import { useState } from "react";

import { type IngestResponse, runExternalIngest, runKofCalendarSync } from "@/lib/api";

type JobName = "external" | "kof";

type JobState = {
  running: JobName | null;
  result: IngestResponse | null;
  error: string | null;
};

function summarizeCounts(result: IngestResponse): string {
  const counts = Object.entries(result.source_counts)
    .map(([source, count]) => `${source}: ${count}`)
    .join(", ");
  return counts || "No source counts returned";
}

export function SourceJobRunner() {
  const [state, setState] = useState<JobState>({ running: null, result: null, error: null });

  async function run(job: JobName) {
    setState({ running: job, result: null, error: null });
    try {
      const result = job === "kof" ? await runKofCalendarSync() : await runExternalIngest();
      setState({ running: null, result, error: null });
    } catch (error) {
      setState({
        running: null,
        result: null,
        error: error instanceof Error ? error.message : "The job failed unexpectedly.",
      });
    }
  }

  return (
    <div className="job-runner">
      <button disabled={state.running !== null} onClick={() => run("kof")} type="button">
        {state.running === "kof" ? "Syncing KOF..." : "Sync KOF calendar"}
      </button>
      <button className="ghost-button" disabled={state.running !== null} onClick={() => run("external")} type="button">
        {state.running === "external" ? "Ingesting..." : "Run external ingest"}
      </button>

      {state.result ? (
        <div className="job-result">
          <strong>
            Created {state.result.created_count}, updated {state.result.updated_count}
          </strong>
          <span>{summarizeCounts(state.result)}</span>
        </div>
      ) : null}

      {state.error ? <p className="source-error">{state.error}</p> : null}
    </div>
  );
}
