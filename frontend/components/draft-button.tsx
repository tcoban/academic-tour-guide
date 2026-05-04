"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createDraft } from "@/lib/api";
import { PurposeButton } from "@/components/purpose-button";

type DraftButtonProps = {
  researcherId: string;
  clusterId: string;
  templateKey?: string;
  label?: string;
  className?: string;
};

export function DraftButton({ researcherId, clusterId, templateKey = "kof_invitation", label = "Create KOF invitation draft", className }: DraftButtonProps) {
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
    <PurposeButton
      className={className}
      errorText={error}
      helperText="Creates one review-gated KOF invitation using approved facts and the selected KOF slot."
      label={label}
      onClick={handleClick}
      pending={pending}
      runningLabel="Creating KOF invitation..."
    />
  );
}
