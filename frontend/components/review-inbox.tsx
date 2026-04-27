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

  async function handleApprove(candidateId: string) {
    try {
      setBusyId(candidateId);
      setError(null);
      await approveFactCandidate(candidateId);
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
            <Link className="ghost-button" href={`/researchers/${candidate.researcher_id}`}>
              Open dossier
            </Link>
          </div>
          <p className="fine-print">Confidence {Math.round(candidate.confidence * 100)}% | {candidate.origin}</p>
          {candidate.evidence_snippet ? <p className="fine-print">{candidate.evidence_snippet}</p> : null}
          {candidate.source_url ? (
            <a className="fine-print" href={candidate.source_url} target="_blank" rel="noreferrer">
              Evidence source
            </a>
          ) : null}
          <div className="timeline-strip">
            <button type="button" onClick={() => handleApprove(candidate.id)} disabled={busyId === candidate.id}>
              {busyId === candidate.id ? "Approving..." : "Approve"}
            </button>
            <button type="button" className="ghost-button" onClick={() => handleReject(candidate.id)} disabled={busyId === candidate.id}>
              Reject
            </button>
          </div>
        </div>
      ))}
      {error ? <p className="fine-print">{error}</p> : null}
    </div>
  );
}
