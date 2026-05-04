"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { enrichResearcher, type EnrichResearcherPayload } from "@/lib/api";

type ManualFactFormProps = {
  researcherId: string;
  defaultHomeInstitution?: string | null;
  requiredFacts?: string[];
};

function optionalText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

const factLabels: Record<string, string> = {
  phd_institution: "PhD institution",
  nationality: "nationality",
  home_institution: "home institution",
  birth_month: "birth month",
};

export function ManualFactForm({ researcherId, defaultHomeInstitution, requiredFacts = [] }: ManualFactFormProps) {
  const router = useRouter();
  const [phdInstitution, setPhdInstitution] = useState("");
  const [nationality, setNationality] = useState("");
  const [homeInstitution, setHomeInstitution] = useState(defaultHomeInstitution ?? "");
  const [birthMonth, setBirthMonth] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [evidenceSnippet, setEvidenceSnippet] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const requiredSet = new Set(requiredFacts);
  const firstRequiredFact = requiredFacts[0];

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
    const missingRequired = requiredFacts.filter((factType) => {
      if (factType === "phd_institution") {
        return !payload.phd_institution;
      }
      if (factType === "nationality") {
        return !payload.nationality;
      }
      if (factType === "home_institution") {
        return !payload.home_institution;
      }
      if (factType === "birth_month") {
        return !payload.birth_month;
      }
      return false;
    });
    if (missingRequired.length) {
      setMessage(`To clear this blocker, add ${missingRequired.map((factType) => factLabels[factType] ?? factType).join(" and ")}.`);
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
      {requiredFacts.length ? (
        <div className="unblock-callout">
          <strong>Clear outreach blocker</strong>
          <p>
            Add {requiredFacts.map((factType) => factLabels[factType] ?? factType).join(" and ")} here. Saving creates approved evidence
            immediately and refreshes draft readiness.
          </p>
        </div>
      ) : null}
      <div className="form-grid">
        <label>
          PhD institution
          <input
            autoFocus={firstRequiredFact === "phd_institution"}
            className={requiredSet.has("phd_institution") ? "input-needs-action" : undefined}
            required={requiredSet.has("phd_institution")}
            value={phdInstitution}
            onChange={(event) => setPhdInstitution(event.target.value)}
            placeholder="University of Mannheim"
          />
        </label>
        <label>
          Nationality
          <input
            autoFocus={firstRequiredFact === "nationality"}
            className={requiredSet.has("nationality") ? "input-needs-action" : undefined}
            required={requiredSet.has("nationality")}
            value={nationality}
            onChange={(event) => setNationality(event.target.value)}
            placeholder="German"
          />
        </label>
        <label>
          Home institution
          <input
            autoFocus={firstRequiredFact === "home_institution"}
            className={requiredSet.has("home_institution") ? "input-needs-action" : undefined}
            required={requiredSet.has("home_institution")}
            value={homeInstitution}
            onChange={(event) => setHomeInstitution(event.target.value)}
            placeholder="MIT"
          />
        </label>
        <label>
          Birth month
          <select
            autoFocus={firstRequiredFact === "birth_month"}
            className={requiredSet.has("birth_month") ? "input-needs-action" : undefined}
            required={requiredSet.has("birth_month")}
            value={birthMonth}
            onChange={(event) => setBirthMonth(event.target.value)}
          >
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
