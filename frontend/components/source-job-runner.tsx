"use client";

import { useState } from "react";

import { type IngestResponse, type SourceHealthRecord, runExternalIngest, runKofCalendarSync, runSourceAudit } from "@/lib/api";

type JobName = "external" | "kof" | "audit";

type JobState = {
  running: JobName | null;
  result: IngestResponse | null;
  auditResult: SourceHealthRecord[] | null;
  error: string | null;
};

function summarizeCounts(result: IngestResponse): string {
  const counts = Object.entries(result.source_counts)
    .map(([source, count]) => `${source}: ${count}`)
    .join(", ");
  return counts || "No source counts returned";
}

export function SourceJobRunner() {
  const [state, setState] = useState<JobState>({ running: null, result: null, auditResult: null, error: null });

  async function run(job: JobName) {
    setState({ running: job, result: null, auditResult: null, error: null });
    try {
      if (job === "audit") {
        const auditResult = await runSourceAudit();
        setState({ running: null, result: null, auditResult, error: null });
        return;
      }
      const result = job === "kof" ? await runKofCalendarSync() : await runExternalIngest();
      setState({ running: null, result, auditResult: null, error: null });
    } catch (error) {
      setState({
        running: null,
        result: null,
        auditResult: null,
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
      <button className="ghost-button" disabled={state.running !== null} onClick={() => run("audit")} type="button">
        {state.running === "audit" ? "Auditing..." : "Record source audit"}
      </button>

      {state.result ? (
        <div className="job-result">
          <strong>
            Created {state.result.created_count}, updated {state.result.updated_count}
          </strong>
          <span>{summarizeCounts(state.result)}</span>
        </div>
      ) : null}

      {state.auditResult ? (
        <div className="job-result">
          <strong>Recorded {state.auditResult.length} source checks</strong>
          <span>
            {state.auditResult
              .map((result) => `${result.source_name}: ${result.event_count}`)
              .join(", ")}
          </span>
        </div>
      ) : null}

      {state.error ? <p className="source-error">{state.error}</p> : null}
    </div>
  );
}
