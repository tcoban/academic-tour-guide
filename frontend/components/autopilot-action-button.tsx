"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Route } from "next";

import { PurposeButton } from "@/components/purpose-button";
import {
  createDraft,
  proposeTourLeg,
  refreshTourLegPrices,
  runEvidenceSearch,
  type OpportunityAutonomyAction,
} from "@/lib/api";

type AutopilotActionButtonProps = {
  action: OpportunityAutonomyAction;
  researcherId: string;
  clusterId: string;
  draftReady: boolean;
  latestTourLegId?: string | null;
  className?: string;
};

function runningLabel(actionKey?: string | null): string {
  if (actionKey === "evidence_search" || actionKey === "biographer_refresh") {
    return "Searching trusted sources...";
  }
  if (actionKey === "propose_tour_leg") {
    return "Building route review...";
  }
  if (actionKey === "refresh_prices") {
    return "Checking first-class fares...";
  }
  if (actionKey === "create_draft") {
    return "Creating KOF invitation...";
  }
  return "Opening action...";
}

export function AutopilotActionButton({
  action,
  researcherId,
  clusterId,
  draftReady,
  latestTourLegId,
  className,
}: AutopilotActionButtonProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const disabledReason =
    action.disabled_reason ||
    (action.action_key === "create_draft" && !draftReady ? "Drafts require approved facts and a selected KOF slot." : null) ||
    (action.action_key === "refresh_prices" && !latestTourLegId ? "Build a route review before checking fares." : null) ||
    (!action.action_key && !action.href ? "No executable action is available for this recommendation." : null);

  async function handleClick() {
    try {
      setPending(true);
      setResult(null);
      setError(null);

      if (action.action_key === "evidence_search" || action.action_key === "biographer_refresh") {
        const summary = await runEvidenceSearch(researcherId);
        setResult(`${summary.created_count} new evidence records, ${summary.updated_count} updated.`);
        router.refresh();
        return;
      }

      if (action.action_key === "propose_tour_leg") {
        const tourLeg = await proposeTourLeg(clusterId);
        router.push(`/tour-legs/${tourLeg.id}`);
        return;
      }

      if (action.action_key === "refresh_prices" && latestTourLegId) {
        await refreshTourLegPrices(latestTourLegId);
        setResult("Fare evidence refreshed for this route review.");
        router.refresh();
        return;
      }

      if (action.action_key === "create_draft") {
        const draft = await createDraft(researcherId, clusterId);
        router.push(`/drafts/${draft.id}`);
        return;
      }

      if (action.href) {
        router.push(action.href as Route);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Autopilot action failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <PurposeButton
      className={className}
      disabledReason={disabledReason}
      errorText={error}
      helperText={action.consequence}
      label={action.label}
      onClick={handleClick}
      pending={pending}
      resultText={result}
      runningLabel={runningLabel(action.action_key)}
    />
  );
}
