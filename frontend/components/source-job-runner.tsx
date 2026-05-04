"use client";

import { useState } from "react";

import { type IngestResponse, type SourceHealthRecord, runExternalIngest, runKofCalendarSync, runSourceAudit } from "@/lib/api";
import { ActionNotice } from "@/components/action-notice";
import { PurposeButton } from "@/components/purpose-button";

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
      <PurposeButton
        disabledReason={state.running && state.running !== "kof" ? "Another sync job is already running." : null}
        helperText="Refreshes occupied KOF events so open slots are not double-booked."
        label="Sync KOF occupied calendar"
        onClick={() => run("kof")}
        pending={state.running === "kof"}
        runningLabel="Syncing KOF calendar..."
      />
      <PurposeButton
        className="ghost-button"
        disabledReason={state.running && state.running !== "external" ? "Another sync job is already running." : null}
        helperText="Fetches watched seminar hubs and clusters new European appearances."
        label="Find new speaker visits"
        onClick={() => run("external")}
        pending={state.running === "external"}
        runningLabel="Finding speaker visits..."
      />
      <PurposeButton
        className="ghost-button"
        disabledReason={state.running && state.running !== "audit" ? "Another sync job is already running." : null}
        helperText="Records source reliability without changing opportunities."
        label="Record data-source status"
        onClick={() => run("audit")}
        pending={state.running === "audit"}
        runningLabel="Recording data-source status..."
      />

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

      {state.error ? (
        <ActionNotice
          severity="error"
          title="Source operation failed"
          explanation={state.error}
          primaryAction={{
            label: "Record data-source status",
            consequence: "Retries the safest read-only audit and records which sources still fail.",
          }}
          primaryActionSlot={
            <PurposeButton
              className="ghost-button"
              disabledReason={state.running && state.running !== "audit" ? "Another sync job is already running." : null}
              helperText="Retries the read-only source audit so the failure is visible in Data Sources."
              label="Record data-source status"
              onClick={() => run("audit")}
              pending={state.running === "audit"}
              runningLabel="Recording data-source status..."
            />
          }
          secondaryActions={[
            {
              label: "Inspect data sources",
              consequence: "Shows the source-level status, official link, parser strategy, and latest error.",
              href: "/source-health",
            },
          ]}
        />
      ) : null}
    </div>
  );
}
