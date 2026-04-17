"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { createOverride, SeminarSlotOverride } from "@/lib/api";

type OverrideManagerProps = {
  overrides: SeminarSlotOverride[];
};

export function OverrideManager({ overrides }: OverrideManagerProps) {
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [status, setStatus] = useState("blocked");
  const [reason, setReason] = useState("Manual scheduling override");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    try {
      await createOverride({
        start_at: startAt,
        end_at: endAt,
        status,
        reason,
      });
      setMessage("Override created. Refresh the page to rebuild the calendar overlay.");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Override creation failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="stack">
      <div className="card-list">
        {overrides.map((override) => (
          <div className="list-card" key={override.id}>
            <div className="panel-header">
              <h3>{override.reason || "Manual override"}</h3>
              <span className={`status-pill ${override.status.toLowerCase() === "blocked" ? "blocked" : ""}`}>
                {override.status}
              </span>
            </div>
            <p className="muted">
              {new Date(override.start_at).toLocaleString()} - {new Date(override.end_at).toLocaleString()}
            </p>
          </div>
        ))}
      </div>
      <form className="stack" onSubmit={handleSubmit}>
        <div className="form-grid">
          <label>
            Start
            <input value={startAt} onChange={(event) => setStartAt(event.target.value)} placeholder="2026-05-05T16:15:00+02:00" />
          </label>
          <label>
            End
            <input value={endAt} onChange={(event) => setEndAt(event.target.value)} placeholder="2026-05-05T17:30:00+02:00" />
          </label>
          <label>
            Status
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="blocked">blocked</option>
              <option value="open">open</option>
            </select>
          </label>
        </div>
        <label>
          Reason
          <input value={reason} onChange={(event) => setReason(event.target.value)} />
        </label>
        <button type="submit" disabled={pending}>
          {pending ? "Saving..." : "Create override"}
        </button>
        {message ? <span className="fine-print">{message}</span> : null}
      </form>
    </div>
  );
}
