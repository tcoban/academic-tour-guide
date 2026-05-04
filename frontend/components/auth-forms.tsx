"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { PurposeButton } from "@/components/purpose-button";
import { loginRoadshowAccount, registerRoadshowAccount } from "@/lib/api";

type AuthMode = "login" | "register";

export function AuthForm({ mode }: { mode: AuthMode }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  function onSubmit(formData: FormData) {
    setError(null);
    setResult(null);
    startTransition(async () => {
      try {
        if (mode === "register") {
          const response = await registerRoadshowAccount({
            email: String(formData.get("email") || ""),
            name: String(formData.get("name") || ""),
            password: String(formData.get("password") || ""),
            institution_name: String(formData.get("institution_name") || ""),
            city: String(formData.get("city") || ""),
            country: String(formData.get("country") || ""),
          });
          setResult(`Created ${response.active_tenant.name}. Opening your Roadshow Start page.`);
        } else {
          const response = await loginRoadshowAccount({
            email: String(formData.get("email") || ""),
            password: String(formData.get("password") || ""),
          });
          setResult(`Signed in to ${response.active_tenant.name}. Opening your Roadshow Start page.`);
        }
        router.refresh();
        router.push("/");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Roadshow could not complete this sign-in action.");
      }
    });
  }

  const isRegister = mode === "register";

  return (
    <form action={onSubmit} className="stack">
      <div className="form-grid">
        <label>
          Email
          <input autoComplete="email" name="email" required type="email" />
        </label>
        {isRegister ? (
          <label>
            Your name
            <input autoComplete="name" name="name" required type="text" />
          </label>
        ) : null}
        <label>
          Password
          <input autoComplete={isRegister ? "new-password" : "current-password"} minLength={8} name="password" required type="password" />
        </label>
      </div>
      {isRegister ? (
        <div className="form-grid">
          <label>
            Institution
            <input name="institution_name" placeholder="Example University" required type="text" />
          </label>
          <label>
            Host city
            <input name="city" placeholder="Zurich" type="text" />
          </label>
          <label>
            Country
            <input name="country" placeholder="Switzerland" type="text" />
          </label>
        </div>
      ) : null}
      <PurposeButton
        errorText={error}
        helperText={isRegister ? "Creates your institution workspace and makes you the owner." : "Starts a secure Roadshow session for your workspace."}
        label={isRegister ? "Create institution workspace" : "Sign in to Roadshow"}
        pending={isPending}
        resultText={result}
        runningLabel={isRegister ? "Creating workspace..." : "Signing in..."}
        type="submit"
      />
    </form>
  );
}
