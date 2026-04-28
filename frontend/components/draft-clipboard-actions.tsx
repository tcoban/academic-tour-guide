"use client";

import { useState } from "react";

type DraftClipboardActionsProps = {
  subject: string;
  body: string;
};

function draftText(subject: string, body: string): string {
  return `Subject: ${subject}\n\n${body}`;
}

export function DraftClipboardActions({ subject, body }: DraftClipboardActionsProps) {
  const [message, setMessage] = useState<string | null>(null);

  async function copyDraft() {
    await navigator.clipboard.writeText(draftText(subject, body));
    setMessage("Draft copied to clipboard.");
  }

  function exportDraft() {
    const blob = new Blob([draftText(subject, body)], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${subject.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "kof-draft"}.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
    setMessage("Draft exported as a text file.");
  }

  return (
    <div className="job-runner">
      <button type="button" onClick={copyDraft}>
        Copy draft
      </button>
      <button className="ghost-button" type="button" onClick={exportDraft}>
        Export .txt
      </button>
      {message ? <span className="fine-print">{message}</span> : null}
    </div>
  );
}
