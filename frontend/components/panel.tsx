import { ReactNode } from "react";

type PanelProps = {
  title: string;
  copy?: string;
  rightSlot?: ReactNode;
  children: ReactNode;
};

export function Panel({ title, copy, rightSlot, children }: PanelProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">{title}</h2>
          {copy ? <p className="panel-copy">{copy}</p> : null}
        </div>
        {rightSlot}
      </div>
      {children}
    </section>
  );
}

