"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createTemplate, deleteTemplate, SeminarSlotTemplate, updateTemplate } from "@/lib/api";

type TemplateManagerProps = {
  templates: SeminarSlotTemplate[];
};

const weekdayLabels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function TemplateManager({ templates }: TemplateManagerProps) {
  const router = useRouter();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [label, setLabel] = useState("KOF Seminar");
  const [weekday, setWeekday] = useState(1);
  const [startTime, setStartTime] = useState("16:15:00");
  const [endTime, setEndTime] = useState("17:30:00");
  const [timezone, setTimezone] = useState("Europe/Zurich");
  const [active, setActive] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function startEditing(template: SeminarSlotTemplate) {
    setEditingId(template.id);
    setLabel(template.label);
    setWeekday(template.weekday);
    setStartTime(template.start_time);
    setEndTime(template.end_time);
    setTimezone(template.timezone);
    setActive(template.active);
    setMessage(null);
  }

  function resetForm() {
    setEditingId(null);
    setLabel("KOF Seminar");
    setWeekday(1);
    setStartTime("16:15:00");
    setEndTime("17:30:00");
    setTimezone("Europe/Zurich");
    setActive(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    try {
      const payload = {
        label,
        weekday,
        start_time: startTime,
        end_time: endTime,
        timezone,
        active,
      };
      if (editingId) {
        await updateTemplate(editingId, payload);
        setMessage("Template updated and availability rebuilt.");
      } else {
        await createTemplate(payload);
        setMessage("Template created and availability rebuilt.");
      }
      resetForm();
      router.refresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Template save failed.");
    } finally {
      setPending(false);
    }
  }

  async function handleDelete(templateId: string) {
    setPending(true);
    try {
      await deleteTemplate(templateId);
      setMessage("Template deleted and availability rebuilt.");
      if (editingId === templateId) {
        resetForm();
      }
      router.refresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Template deletion failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="stack">
      <div className="card-list">
        {templates.map((template) => (
          <div className="list-card" key={template.id}>
            <div className="panel-header">
              <div>
                <h3>{template.label}</h3>
                <p className="muted">
                  {weekdayLabels[template.weekday]} {template.start_time.slice(0, 5)} - {template.end_time.slice(0, 5)} ({template.timezone})
                </p>
                <p className="fine-print">{template.active ? "Active" : "Inactive"}</p>
              </div>
              <div className="template-actions">
                <button className="ghost-button" disabled={pending} onClick={() => startEditing(template)} type="button">
                  Edit
                </button>
                <button className="ghost-button" disabled={pending} onClick={() => handleDelete(template.id)} type="button">
                  Delete
                </button>
              </div>
            </div>
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
        <label className="inline-check">
          <input checked={active} onChange={(event) => setActive(event.target.checked)} type="checkbox" />
          Active template
        </label>
        <div className="template-actions">
          <button type="submit" disabled={pending}>
            {pending ? "Saving..." : editingId ? "Update template" : "Create template"}
          </button>
          {editingId ? (
            <button className="ghost-button" onClick={resetForm} type="button">
              Cancel edit
            </button>
          ) : null}
        </div>
        {message ? <span className="fine-print">{message}</span> : null}
      </form>
    </div>
  );
}
