"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createWishlistEntry, deleteWishlistEntry, Researcher, updateWishlistEntry, WishlistEntry } from "@/lib/api";

type WishlistManagerProps = {
  entries: WishlistEntry[];
  researchers: Researcher[];
  kofInstitutionId: string;
};

export function WishlistManager({ entries, researchers, kofInstitutionId }: WishlistManagerProps) {
  const router = useRouter();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [researcherId, setResearcherId] = useState("");
  const [speakerName, setSpeakerName] = useState("");
  const [topic, setTopic] = useState("");
  const [priority, setPriority] = useState(80);
  const [status, setStatus] = useState("active");
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function resetForm() {
    setEditingId(null);
    setResearcherId("");
    setSpeakerName("");
    setTopic("");
    setPriority(80);
    setStatus("active");
    setNotes("");
  }

  function startEditing(entry: WishlistEntry) {
    setEditingId(entry.id);
    setResearcherId(entry.researcher_id || "");
    setSpeakerName(entry.speaker_name || "");
    setTopic(entry.topic || "");
    setPriority(entry.priority);
    setStatus(entry.status);
    setNotes(entry.notes || "");
    setMessage(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    try {
      const payload = {
        institution_id: kofInstitutionId,
        researcher_id: researcherId || null,
        speaker_name: speakerName || null,
        topic: topic || null,
        priority,
        status,
        notes: notes || null,
        metadata_json: { source: "roadshow_admin" },
      };
      if (editingId) {
        await updateWishlistEntry(editingId, payload);
        setMessage("Wishlist entry updated and alerts refreshed.");
      } else {
        await createWishlistEntry(payload);
        setMessage("Wishlist entry created and alerts refreshed.");
      }
      resetForm();
      router.refresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Wishlist save failed.");
    } finally {
      setPending(false);
    }
  }

  async function handleDelete(entryId: string) {
    setPending(true);
    try {
      await deleteWishlistEntry(entryId);
      setMessage("Wishlist entry deleted.");
      if (editingId === entryId) {
        resetForm();
      }
      router.refresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Wishlist delete failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="stack">
      <div className="card-list">
        {entries.map((entry) => (
          <div className="list-card" key={entry.id}>
            <div className="panel-header">
              <div>
                <h3>{entry.speaker_name || researchers.find((researcher) => researcher.id === entry.researcher_id)?.name || "Topic watch"}</h3>
                <p className="muted">{entry.topic || "No topic filter"} | Priority {entry.priority}</p>
                {entry.notes ? <p className="fine-print">{entry.notes}</p> : null}
              </div>
              <div className="template-actions">
                <span className="status-pill">{entry.status}</span>
                <button className="ghost-button" disabled={pending} onClick={() => startEditing(entry)} type="button">
                  Edit wishlist watch
                </button>
                <button className="ghost-button" disabled={pending} onClick={() => handleDelete(entry.id)} type="button">
                  Delete wishlist watch
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <form className="stack" onSubmit={handleSubmit}>
        <div className="form-grid">
          <label>
            Linked speaker
            <select value={researcherId} onChange={(event) => setResearcherId(event.target.value)}>
              <option value="">No linked speaker</option>
              {researchers.map((researcher) => (
                <option key={researcher.id} value={researcher.id}>
                  {researcher.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Speaker name
            <input value={speakerName} onChange={(event) => setSpeakerName(event.target.value)} placeholder="Prof. Example" />
          </label>
          <label>
            Topic
            <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="macro networks" />
          </label>
        </div>
        <div className="form-grid">
          <label>
            Priority
            <input min={0} max={100} type="number" value={priority} onChange={(event) => setPriority(Number(event.target.value))} />
          </label>
          <label>
            Status
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="active">active</option>
              <option value="paused">paused</option>
              <option value="archived">archived</option>
            </select>
          </label>
        </div>
        <label>
          Notes
          <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Why KOF wants this speaker or topic" />
        </label>
        <div className="template-actions">
          <button disabled={pending} type="submit">
            {pending ? "Saving watch..." : editingId ? "Update wishlist watch" : "Add speaker/topic watch"}
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
