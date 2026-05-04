"use client";

import { ApiOfflineState } from "@/components/api-offline-state";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="stack">
      <ApiOfflineState message={error.message} />
      <button className="ghost-button retry-button" onClick={reset} type="button">
        Try loading Roadshow again
      </button>
    </div>
  );
}
