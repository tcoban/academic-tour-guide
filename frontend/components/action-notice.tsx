import Link from "next/link";
import type { Route } from "next";
import type { ReactNode } from "react";

export type ActionNoticeSeverity = "info" | "warning" | "blocked" | "error";

export type ActionNoticeAction = {
  label: string;
  consequence: string;
  href?: string | null;
  external?: boolean;
  disabledReason?: string | null;
  className?: string;
};

type ActionNoticeProps = {
  severity: ActionNoticeSeverity;
  title: string;
  explanation: string;
  primaryAction: ActionNoticeAction;
  primaryActionSlot?: ReactNode;
  secondaryActions?: ActionNoticeAction[];
  resultText?: ReactNode;
  errorText?: ReactNode;
};

function NoticeAction({ action, primary = false }: { action: ActionNoticeAction; primary?: boolean }) {
  const className = action.className ?? (primary ? "button-link" : "ghost-button");
  const consequence = <span className="fine-print notice-action-consequence">{action.consequence}</span>;

  if (action.disabledReason) {
    return (
      <div className="purpose-action">
        <button disabled type="button">
          {action.label}
        </button>
        <span className="fine-print action-blocker">{action.disabledReason}</span>
        {consequence}
      </div>
    );
  }

  if (action.href) {
    if (action.external) {
      return (
        <div className="purpose-action">
          <a className={className} href={action.href} rel="noreferrer" target="_blank">
            {action.label}
          </a>
          {consequence}
        </div>
      );
    }
    return (
      <div className="purpose-action">
        <Link className={className} href={action.href as Route}>
          {action.label}
        </Link>
        {consequence}
      </div>
    );
  }

  return (
    <div className="purpose-action">
      <button className={className} disabled type="button">
        {action.label}
      </button>
      <span className="fine-print action-blocker">No safe inline action is available for this notice.</span>
      {consequence}
    </div>
  );
}

export function ActionNotice({
  severity,
  title,
  explanation,
  primaryAction,
  primaryActionSlot,
  secondaryActions = [],
  resultText,
  errorText,
}: ActionNoticeProps) {
  return (
    <div className={`action-notice ${severity}`} data-action-notice="true">
      <div className="action-notice-copy">
        <span className={`status-pill ${severity === "info" ? "" : severity}`}>{severity.replaceAll("_", " ")}</span>
        <h3>{title}</h3>
        <p className="muted">{explanation}</p>
      </div>
      <div className="action-notice-actions">
        {primaryActionSlot ?? <NoticeAction action={primaryAction} primary />}
        {secondaryActions.map((action) => (
          <NoticeAction action={action} key={`${action.label}-${action.href ?? action.consequence}`} />
        ))}
      </div>
      {resultText ? <p className="fine-print action-result">{resultText}</p> : null}
      {errorText ? <p className="fine-print action-error">{errorText}</p> : null}
    </div>
  );
}
