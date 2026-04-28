"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createFeedbackSignal } from "@/lib/api";

type FeedbackSignalFormProps = {
  researcherId: string;
  institutionId: string;
  tourLegId?: string | null;
};

export function FeedbackSignalForm({ researcherId, institutionId, tourLegId = null }: FeedbackSignalFormProps) {
  const router = useRouter();
  const [party, setParty] = useState("institution");
  const [signalType, setSignalType] = useState("host_quality");
  const [value, setValue] = useState("");
  const [sentimentScore, setSentimentScore] = useState("0.5");
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    try {
      await createFeedbackSignal({
        researcher_id: researcherId,
        institution_id: institutionId,
        tour_leg_id: tourLegId,
        party,
        signal_type: signalType,
        value,
        sentiment_score: Number(sentimentScore),
        notes: notes || null,
        metadata_json: { source: "manual_admin_capture" },
      });
      setValue("");
      setNotes("");
      setMessage("Feedback signal saved and relationship memory updated.");
      router.refresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Feedback save failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="stack" onSubmit={handleSubmit}>
      <div className="form-grid">
        <label>
          Party
          <select value={party} onChange={(event) => setParty(event.target.value)}>
            <option value="institution">institution</option>
            <option value="speaker">speaker</option>
          </select>
        </label>
        <label>
          Signal type
          <input value={signalType} onChange={(event) => setSignalType(event.target.value)} />
        </label>
        <label>
          Sentiment
          <input min={-1} max={1} step={0.1} type="number" value={sentimentScore} onChange={(event) => setSentimentScore(event.target.value)} />
        </label>
      </div>
      <label>
        Value
        <input required value={value} onChange={(event) => setValue(event.target.value)} placeholder="e.g. strong re-book intent" />
      </label>
      <label>
        Notes
        <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Short operator context" />
      </label>
      <button disabled={pending} type="submit">
        {pending ? "Saving..." : "Capture feedback signal"}
      </button>
      {message ? <span className="fine-print">{message}</span> : null}
    </form>
  );
}
