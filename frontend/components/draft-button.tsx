"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createDraft } from "@/lib/api";

type DraftButtonProps = {
  researcherId: string;
  clusterId: string;
  templateKey?: string;
  label?: string;
  className?: string;
};

export function DraftButton({ researcherId, clusterId, templateKey = "concierge", label = "One-Click Draft", className }: DraftButtonProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    try {
      setPending(true);
      setError(null);
      const draft = await createDraft(researcherId, clusterId, templateKey);
      router.push(`/drafts/${draft.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Draft creation failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="stack">
      <button className={className} type="button" onClick={handleClick} disabled={pending}>
        {pending ? "Drafting..." : label}
      </button>
      {error ? <span className="fine-print">{error}</span> : null}
    </div>
  );
}
