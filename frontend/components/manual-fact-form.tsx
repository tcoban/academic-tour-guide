"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { enrichResearcher, type EnrichResearcherPayload } from "@/lib/api";

type ManualFactFormProps = {
  researcherId: string;
  defaultHomeInstitution?: string | null;
};

function optionalText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export function ManualFactForm({ researcherId, defaultHomeInstitution }: ManualFactFormProps) {
  const router = useRouter();
  const [phdInstitution, setPhdInstitution] = useState("");
  const [nationality, setNationality] = useState("");
  const [homeInstitution, setHomeInstitution] = useState(defaultHomeInstitution ?? "");
  const [birthMonth, setBirthMonth] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [evidenceSnippet, setEvidenceSnippet] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload: EnrichResearcherPayload = {
      phd_institution: optionalText(phdInstitution),
      nationality: optionalText(nationality),
      home_institution: optionalText(homeInstitution),
      birth_month: birthMonth ? Number(birthMonth) : null,
      source_url: optionalText(sourceUrl),
      evidence_snippet: optionalText(evidenceSnippet),
    };
    const hasFact = Boolean(payload.phd_institution || payload.nationality || payload.home_institution || payload.birth_month);
    if (!hasFact) {
      setMessage("Add at least one fact before saving.");
      return;
    }

    try {
      setPending(true);
      setMessage(null);
      await enrichResearcher(researcherId, payload);
      setPhdInstitution("");
      setNationality("");
      setBirthMonth("");
      setSourceUrl("");
      setEvidenceSnippet("");
      setMessage("Approved facts saved. The dossier and outreach readiness were refreshed.");
      router.refresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Manual enrichment failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="stack" onSubmit={handleSubmit}>
      <div className="form-grid">
        <label>
          PhD institution
          <input value={phdInstitution} onChange={(event) => setPhdInstitution(event.target.value)} placeholder="University of Mannheim" />
        </label>
        <label>
          Nationality
          <input value={nationality} onChange={(event) => setNationality(event.target.value)} placeholder="German" />
        </label>
        <label>
          Home institution
          <input value={homeInstitution} onChange={(event) => setHomeInstitution(event.target.value)} placeholder="MIT" />
        </label>
        <label>
          Birth month
          <select value={birthMonth} onChange={(event) => setBirthMonth(event.target.value)}>
            <option value="">Unknown</option>
            {Array.from({ length: 12 }, (_, index) => (
              <option key={index + 1} value={index + 1}>
                {index + 1}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label>
        Evidence source URL
        <input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://..." />
      </label>

      <label>
        Evidence snippet or admin note
        <textarea
          value={evidenceSnippet}
          onChange={(event) => setEvidenceSnippet(event.target.value)}
          placeholder="Short quote or note explaining why this fact is trusted."
        />
      </label>

      <div className="template-actions">
        <button type="submit" disabled={pending}>
          {pending ? "Saving..." : "Save approved facts"}
        </button>
      </div>
      {message ? <p className="fine-print">{message}</p> : null}
    </form>
  );
}
