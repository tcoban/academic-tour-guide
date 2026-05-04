import Link from "next/link";
import type { Route } from "next";

import { AuthForm } from "@/components/auth-forms";
import { Panel } from "@/components/panel";

export const dynamic = "force-dynamic";

export default function RegisterPage() {
  return (
    <main className="page-grid">
      <section className="hero-panel">
        <span className="eyebrow">Institution onboarding</span>
        <h1>Create a Roadshow workspace for your seminar desk.</h1>
        <p className="hero-copy">
          Registration creates an institution tenant, host profile, owner membership, and the first private workspace for slots,
          wishlists, drafts, and tour planning.
        </p>
      </section>
      <Panel title="Create workspace">
        <AuthForm mode="register" />
        <p className="fine-print">
          Already have access? <Link href={"/login" as Route}>Sign in to Roadshow</Link>.
        </p>
      </Panel>
    </main>
  );
}
