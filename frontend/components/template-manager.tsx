"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { createTemplate, SeminarSlotTemplate } from "@/lib/api";

type TemplateManagerProps = {
  templates: SeminarSlotTemplate[];
};

const weekdayLabels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function TemplateManager({ templates }: TemplateManagerProps) {
  const [label, setLabel] = useState("KOF Seminar");
  const [weekday, setWeekday] = useState(1);
  const [startTime, setStartTime] = useState("16:15:00");
  const [endTime, setEndTime] = useState("17:30:00");
  const [timezone, setTimezone] = useState("Europe/Zurich");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    try {
      await createTemplate({
        label,
        weekday,
        start_time: startTime,
        end_time: endTime,
        timezone,
        active: true,
      });
      setMessage("Template created. Refresh the page to see the derived windows.");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Template creation failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="stack">
      <div className="card-list">
        {templates.map((template) => (
          <div className="list-card" key={template.id}>
            <h3>{template.label}</h3>
            <p className="muted">
              {weekdayLabels[template.weekday]} {template.start_time.slice(0, 5)} - {template.end_time.slice(0, 5)} ({template.timezone})
            </p>
          </div>
        ))}
      </div>
      <form className="stack" onSubmit={handleSubmit}>
        <div className="form-grid">
          <label>
            Label
            <input value={label} onChange={(event) => setLabel(event.target.value)} />
          </label>
          <label>
            Weekday
            <select value={weekday} onChange={(event) => setWeekday(Number(event.target.value))}>
              {weekdayLabels.map((weekdayLabel, index) => (
                <option value={index} key={weekdayLabel}>
                  {weekdayLabel}
                </option>
              ))}
            </select>
          </label>
          <label>
            Start time
            <input value={startTime} onChange={(event) => setStartTime(event.target.value)} />
          </label>
          <label>
            End time
            <input value={endTime} onChange={(event) => setEndTime(event.target.value)} />
          </label>
        </div>
        <label>
          Timezone
          <input value={timezone} onChange={(event) => setTimezone(event.target.value)} />
        </label>
        <button type="submit" disabled={pending}>
          {pending ? "Saving..." : "Create template"}
        </button>
        {message ? <span className="fine-print">{message}</span> : null}
      </form>
    </div>
  );
}
