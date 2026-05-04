"use client";

import type { ReactNode } from "react";

type PurposeButtonProps = {
  label: string;
  runningLabel?: string;
  helperText?: ReactNode;
  resultText?: ReactNode;
  errorText?: ReactNode;
  disabledReason?: string | null;
  className?: string;
  pending?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
};

export function PurposeButton({
  label,
  runningLabel,
  helperText,
  resultText,
  errorText,
  disabledReason,
  className,
  pending = false,
  onClick,
  type = "button",
}: PurposeButtonProps) {
  const disabled = pending || Boolean(disabledReason);

  return (
    <div className="purpose-action">
      <button className={className} disabled={disabled} onClick={onClick} type={type}>
        {pending ? runningLabel || `${label}...` : label}
      </button>
      {disabledReason ? <span className="fine-print action-blocker">{disabledReason}</span> : null}
      {!disabledReason && helperText ? <span className="fine-print">{helperText}</span> : null}
      {resultText ? <span className="fine-print action-result">{resultText}</span> : null}
      {errorText ? <span className="fine-print action-error">{errorText}</span> : null}
    </div>
  );
}
