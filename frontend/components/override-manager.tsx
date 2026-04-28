"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createOverride, deleteOverride, SeminarSlotOverride, updateOverride } from "@/lib/api";

type OverrideManagerProps = {
  overrides: SeminarSlotOverride[];
};

export function OverrideManager({ overrides }: OverrideManagerProps) {
  const router = useRouter();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [status, setStatus] = useState("blocked");
  const [reason, setReason] = useState("Manual scheduling override");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function startEditing(override: SeminarSlotOverride) {
    setEditingId(override.id);
    setStartAt(override.start_at);
    setEndAt(override.end_at);
    setStatus(override.status);
    setReason(override.reason || "Manual scheduling override");
    setMessage(null);
  }

  function resetForm() {
    setEditingId(null);
    setStartAt("");
    setEndAt("");
    setStatus("blocked");
    setReason("Manual scheduling override");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    try {
      const payload = {
        start_at: startAt,
        end_at: endAt,
        status,
        reason,
      };
      if (editingId) {
        await updateOverride(editingId, payload);
        setMessage("Override updated and availability rebuilt.");
      } else {
        await createOverride(payload);
        setMessage("Override created and availability rebuilt.");
      }
      resetForm();
      router.refresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Override save failed.");
    } finally {
      setPending(false);
    }
  }

  async function handleDelete(overrideId: string) {
    setPending(true);
    try {
      await deleteOverride(overrideId);
      setMessage("Override deleted and availability rebuilt.");
      if (editingId === overrideId) {
        resetForm();
      }
      router.refresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Override deletion failed.");
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
              <div>
                <h3>{override.reason || "Manual override"}</h3>
                <p className="muted">
                  {new Date(override.start_at).toLocaleString()} - {new Date(override.end_at).toLocaleString()}
                </p>
              </div>
              <div className="template-actions">
                <span className={`status-pill ${override.status.toLowerCase() === "blocked" ? "blocked" : ""}`}>
                  {override.status}
                </span>
                <button className="ghost-button" disabled={pending} onClick={() => startEditing(override)} type="button">
                  Edit
                </button>
                <button className="ghost-button" disabled={pending} onClick={() => handleDelete(override.id)} type="button">
                  Delete
                </button>
              </div>
            </div>
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
        <div className="template-actions">
          <button type="submit" disabled={pending}>
            {pending ? "Saving..." : editingId ? "Update override" : "Create override"}
          </button>
          {editingId ? (
            <button className="ghost-button" onClick={resetForm} type="button">
              Cancel edit
            </button>
          ) : null}
        </div>
        {message ? <span className="fine-print">{message}</span> : null}
      </form>
    </div>
  );
}
