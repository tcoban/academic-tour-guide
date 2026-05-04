"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PurposeButton } from "@/components/purpose-button";
import { refreshTourLegPrices } from "@/lib/api";

type RefreshPricesButtonProps = {
  tourLegId: string;
  label?: string;
  className?: string;
  helperText?: string;
};

export function RefreshPricesButton({
  tourLegId,
  label = "Refresh live prices",
  className = "ghost-button",
  helperText = "Checks authorized fare providers first, then marks conservative estimates for review.",
}: RefreshPricesButtonProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    try {
      setPending(true);
      setError(null);
      await refreshTourLegPrices(tourLegId);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Price refresh failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <PurposeButton
      className={className}
      errorText={error}
      helperText={helperText}
      label={label}
      onClick={handleClick}
      pending={pending}
      runningLabel="Checking fares..."
    />
  );
}
