"use client";

import { useState } from "react";

import { PurposeButton } from "@/components/purpose-button";
import { runAiAutopilotPlan, type AIAutopilotPlan } from "@/lib/api";

export function AiAutopilotPlanButton({ className }: { className?: string }) {
  const [running, setRunning] = useState(false);
  const [plan, setPlan] = useState<AIAutopilotPlan | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    try {
      setRunning(true);
      setPlan(null);
      setError(null);
      setPlan(await runAiAutopilotPlan());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "AI autopilot plan failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <PurposeButton
      className={className}
      errorText={error}
      helperText="Asks Roadshow AI for one next action, then keeps only backend-validated actions."
      label="Ask AI for next action"
      onClick={handleClick}
      pending={running}
      resultText={plan ? `${plan.explanation} Suggested action: ${plan.action.label}.` : null}
      runningLabel="Checking AI next action..."
    />
  );
}
