"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { PurposeButton } from "@/components/purpose-button";
import { updateCurrentTenant, updateCurrentTenantSettings, type Tenant, type TenantSettings } from "@/lib/api";

export function TenantSettingsForm({ tenant, settings }: { tenant: Tenant; settings: TenantSettings }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  function onSubmit(formData: FormData) {
    setError(null);
    setResult(null);
    startTransition(async () => {
      try {
        const focuses = String(formData.get("research_focuses") || "")
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean);
        await updateCurrentTenant({
          name: String(formData.get("name") || tenant.name),
          city: String(formData.get("city") || ""),
          country: String(formData.get("country") || ""),
          timezone: String(formData.get("timezone") || tenant.timezone),
          currency: String(formData.get("currency") || tenant.currency),
          anonymous_matching_opt_in: formData.get("anonymous_matching_opt_in") === "on",
        });
        await updateCurrentTenantSettings({ research_focuses: focuses });
        setResult("Workspace settings saved. Future scoring and matching use these tenant priorities.");
        router.refresh();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Roadshow could not save these workspace settings.");
      }
    });
  }

  return (
    <form action={onSubmit} className="stack">
      <div className="form-grid">
        <label>
          Institution display name
          <input defaultValue={tenant.name} name="name" required type="text" />
        </label>
        <label>
          Host city
          <input defaultValue={tenant.city ?? ""} name="city" type="text" />
        </label>
        <label>
          Country
          <input defaultValue={tenant.country ?? ""} name="country" type="text" />
        </label>
        <label>
          Timezone
          <input defaultValue={tenant.timezone} name="timezone" required type="text" />
        </label>
        <label>
          Currency
          <input defaultValue={tenant.currency} name="currency" required type="text" />
        </label>
      </div>
      <label>
        Research priorities, one per line
        <textarea defaultValue={(settings.research_focuses || []).join("\n")} name="research_focuses" />
      </label>
      <label className="inline-check">
        <input defaultChecked={tenant.anonymous_matching_opt_in} name="anonymous_matching_opt_in" type="checkbox" />
        Allow anonymous co-host matching with nearby opted-in institutions
      </label>
      <PurposeButton
        errorText={error}
        helperText="Updates host context, research-fit scoring priorities, and anonymous matching eligibility."
        label="Save workspace settings"
        pending={isPending}
        resultText={result}
        runningLabel="Saving workspace settings..."
        type="submit"
      />
    </form>
  );
}
