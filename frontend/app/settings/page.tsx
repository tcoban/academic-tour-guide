import Link from "next/link";
import type { Route } from "next";

import { ApiOfflineState } from "@/components/api-offline-state";
import { Panel } from "@/components/panel";
import { TenantSettingsForm } from "@/components/tenant-settings-form";
import { getCurrentTenant, getCurrentTenantSettings, getMe, getTenantSourceSubscriptions, RoadshowApiError } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  try {
    const [me, tenant, settings, subscriptions] = await Promise.all([
      getMe(),
      getCurrentTenant(),
      getCurrentTenantSettings(),
      getTenantSourceSubscriptions(),
    ]);

    return (
      <main className="page-grid">
        <section className="hero-panel">
          <span className="eyebrow">Workspace settings</span>
          <h1>{tenant.name}</h1>
          <p className="hero-copy">
            Configure the host context Roadshow uses for scoring, invitation language, slot matching, source subscriptions,
            and anonymous co-host eligibility.
          </p>
          {!me.authenticated ? (
            <p className="fine-print">
              You are viewing the default workspace context. <Link href={"/login" as Route}>Sign in</Link> to manage a private institution workspace.
            </p>
          ) : null}
        </section>
        <Panel title="Institution context">
          <TenantSettingsForm settings={settings} tenant={tenant} />
        </Panel>
        <Panel title="Source subscriptions">
          {subscriptions.length ? (
            <div className="guided-list compact">
              {subscriptions.map((subscription) => (
                <article className="guided-item" key={subscription.id}>
                  <span className="status-pill">{subscription.status}</span>
                  <div>
                    <h3>{subscription.source_name}</h3>
                    <p className="muted">{subscription.notes || "Included in this workspace's source sync plan."}</p>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <h3>No source subscriptions yet.</h3>
              <p className="muted">Roadshow can still use global public intelligence, but tenant-specific source preferences are not configured.</p>
            </div>
          )}
        </Panel>
      </main>
    );
  } catch (error) {
    if (error instanceof RoadshowApiError) {
      return <ApiOfflineState message={error.message} />;
    }
    throw error;
  }
}
