"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { proposeTourLeg } from "@/lib/api";
import { PurposeButton } from "@/components/purpose-button";

type TourLegButtonProps = {
  clusterId: string;
  className?: string;
  label?: string;
};

export function TourLegButton({ clusterId, className = "ghost-button", label = "Add KOF as a tour stop" }: TourLegButtonProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    try {
      setPending(true);
      setError(null);
      const tourLeg = await proposeTourLeg(clusterId);
      router.push(`/tour-legs/${tourLeg.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Tour-leg proposal failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <PurposeButton
      className={className}
      errorText={error}
      helperText="Builds a KOF stop with adjacent travel split and Zurich hospitality; no speaker fee is assumed."
      label={label}
      onClick={handleClick}
      pending={pending}
      runningLabel="Modeling KOF stop..."
    />
  );
}
