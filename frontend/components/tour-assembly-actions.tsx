"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PurposeButton } from "@/components/purpose-button";
import { ACTION_LABELS } from "@/lib/action-labels";
import { createTourAssemblySpeakerDraft, proposeTourAssembly, refreshWishlistMatches, updateWishlistMatchStatus } from "@/lib/api";

type TourAssemblyProposalButtonProps = {
  matchGroupId: string;
  disabledReason?: string | null;
};

export function TourAssemblyProposalButton({ matchGroupId, disabledReason }: TourAssemblyProposalButtonProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    try {
      setPending(true);
      setError(null);
      const proposal = await proposeTourAssembly(matchGroupId);
      router.push(`/tour-assemblies/${proposal.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Anonymous tour proposal could not be built.");
    } finally {
      setPending(false);
    }
  }

  return (
    <PurposeButton
      className="primary-button"
      disabledReason={disabledReason}
      errorText={error}
      helperText="Creates a masked term sheet, budget screen, ordered stops, and review blockers."
      label={ACTION_LABELS.buildAnonymousTourProposal}
      onClick={handleClick}
      pending={pending}
      runningLabel="Building anonymous tour..."
    />
  );
}

type TourAssemblyDraftButtonProps = {
  proposalId: string;
  disabledReason?: string | null;
};

export function TourAssemblyDraftButton({ proposalId, disabledReason }: TourAssemblyDraftButtonProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    try {
      setPending(true);
      setError(null);
      const draft = await createTourAssemblySpeakerDraft(proposalId);
      router.push(`/drafts/${draft.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Speaker tour draft could not be created.");
    } finally {
      setPending(false);
    }
  }

  return (
    <PurposeButton
      className="primary-button"
      disabledReason={disabledReason}
      errorText={error}
      helperText="Generates a review-gated speaker request for the masked multi-host tour."
      label={ACTION_LABELS.createSpeakerTourDraft}
      onClick={handleClick}
      pending={pending}
      runningLabel="Creating speaker tour draft..."
    />
  );
}

export function RefreshWishlistMatchesButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    try {
      setPending(true);
      setError(null);
      const matches = await refreshWishlistMatches();
      setResult(`${matches.length} anonymous match${matches.length === 1 ? "" : "es"} refreshed.`);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Wishlist matching could not be refreshed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <PurposeButton
      className="ghost-button"
      errorText={error}
      helperText="Rechecks active speaker-specific wishlist entries against the 150 km co-host rule."
      label="Refresh anonymous matches"
      onClick={handleClick}
      pending={pending}
      resultText={result}
      runningLabel="Refreshing matches..."
    />
  );
}

type DismissWishlistMatchButtonProps = {
  matchGroupId: string;
};

export function DismissWishlistMatchButton({ matchGroupId }: DismissWishlistMatchButtonProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    try {
      setPending(true);
      setError(null);
      await updateWishlistMatchStatus(matchGroupId, "dismissed", "Dismissed from the wishlist match queue.");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Wishlist match could not be dismissed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <PurposeButton
      className="ghost-button"
      errorText={error}
      helperText="Removes this masked match from the active co-host queue."
      label="Dismiss co-host match"
      onClick={handleClick}
      pending={pending}
      runningLabel="Dismissing match..."
    />
  );
}
