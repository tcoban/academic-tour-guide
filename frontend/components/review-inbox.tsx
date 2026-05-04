"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { approveFactCandidate, rejectFactCandidate, type ReviewFact } from "@/lib/api";

type ReviewInboxProps = {
  candidates: ReviewFact[];
};

export function ReviewInbox({ candidates }: ReviewInboxProps) {
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mergedValues, setMergedValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(candidates.map((candidate) => [candidate.id, candidate.value])),
  );

  function updateMergedValue(candidateId: string, value: string) {
    setMergedValues((current) => ({ ...current, [candidateId]: value }));
  }

  async function handleApprove(candidate: ReviewFact) {
    const mergedValue = (mergedValues[candidate.id] ?? candidate.value).trim();
    if (!mergedValue) {
      setError("Approved value cannot be empty.");
      return;
    }

    try {
      setBusyId(candidate.id);
      setError(null);
      await approveFactCandidate(candidate.id, mergedValue === candidate.value ? undefined : mergedValue);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Approval failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(candidateId: string) {
    try {
      setBusyId(candidateId);
      setError(null);
      await rejectFactCandidate(candidateId, "Rejected from review inbox.");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Rejection failed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="card-list">
      {candidates.map((candidate) => (
        <div className="list-card" key={candidate.id}>
          <div className="panel-header">
            <div>
              <h3>{candidate.researcher_name}</h3>
              <p className="muted">
                {candidate.fact_type}: {candidate.value}
              </p>
            </div>
            <div className="template-actions">
              <span className={`status-pill ${candidate.status === "rejected" ? "blocked" : candidate.status === "pending" ? "warning" : ""}`}>
                {candidate.status}
              </span>
              <Link className="ghost-button" href={`/researchers/${candidate.researcher_id}`}>
                Inspect speaker evidence
              </Link>
            </div>
          </div>
          <p className="fine-print">Confidence {Math.round(candidate.confidence * 100)}% | {candidate.origin}</p>
          {candidate.reviewed_at ? <p className="fine-print">Reviewed {new Date(candidate.reviewed_at).toLocaleString()}</p> : null}
          {candidate.review_note ? <p className="fine-print">Review note: {candidate.review_note}</p> : null}
          {candidate.evidence_snippet ? <p className="fine-print">{candidate.evidence_snippet}</p> : null}
          {candidate.source_url ? (
            <a className="fine-print" href={candidate.source_url} target="_blank" rel="noreferrer">
              Evidence source
            </a>
          ) : null}
          {candidate.status === "pending" ? (
            <>
              <label>
                Approved value
                <input
                  value={mergedValues[candidate.id] ?? candidate.value}
                  onChange={(event) => updateMergedValue(candidate.id, event.target.value)}
                />
              </label>
              <div className="timeline-strip">
                <button type="button" onClick={() => handleApprove(candidate)} disabled={busyId === candidate.id}>
                  {busyId === candidate.id ? "Approving..." : "Approve value"}
                </button>
                <button type="button" className="ghost-button" onClick={() => handleReject(candidate.id)} disabled={busyId === candidate.id}>
                  Reject evidence candidate
                </button>
              </div>
            </>
          ) : null}
        </div>
      ))}
      {error ? <p className="fine-print">{error}</p> : null}
    </div>
  );
}
