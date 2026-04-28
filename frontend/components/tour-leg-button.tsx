"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { proposeTourLeg } from "@/lib/api";

type TourLegButtonProps = {
  clusterId: string;
  className?: string;
  label?: string;
};

export function TourLegButton({ clusterId, className = "ghost-button", label = "Propose tour leg" }: TourLegButtonProps) {
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
    <div className="stack">
      <button className={className} disabled={pending} onClick={handleClick} type="button">
        {pending ? "Modeling..." : label}
      </button>
      {error ? <span className="fine-print">{error}</span> : null}
    </div>
  );
}
