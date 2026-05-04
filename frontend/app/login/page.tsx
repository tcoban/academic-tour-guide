import Link from "next/link";
import type { Route } from "next";

import { AuthForm } from "@/components/auth-forms";
import { Panel } from "@/components/panel";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  return (
    <main className="page-grid">
      <section className="hero-panel">
        <span className="eyebrow">Self-service access</span>
        <h1>Sign in to your Roadshow workspace.</h1>
        <p className="hero-copy">
          Roadshow now keeps slots, wishlists, drafts, route reviews, and relationship memory separated by institution.
        </p>
      </section>
      <Panel title="Roadshow login">
        <AuthForm mode="login" />
        <p className="fine-print">
          New institution? <Link href={"/register" as Route}>Create a Roadshow workspace</Link>.
        </p>
      </Panel>
    </main>
  );
}
