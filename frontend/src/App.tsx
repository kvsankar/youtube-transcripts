import { useEffect, useMemo, useState } from "react";
import {
  createJobs,
  deleteJob,
  setJobTags,
  subscribeEvents,
} from "./api";
import { confirmAndDelete } from "./confirmRemove";
import { Splitter } from "./Splitter";
import { Viewer } from "./Viewer";
import type { Job, JobStatus } from "./types";

const STAGE_LABEL: Record<JobStatus, string> = {
  queued: "Queued",
  downloading: "Downloading",
  transcribing: "Transcribing",
  structuring: "Structuring",
  summarizing: "Summarizing",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function App() {
  const [urlInput, setUrlInput] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  useEffect(() => {
    return subscribeEvents((event) => {
      setJobs((prev) => {
        const next = { ...prev };
        switch (event.type) {
          case "snapshot":
            return Object.fromEntries(event.jobs.map((j) => [j.id, j]));
          case "job.created":
          case "job.updated":
            next[event.job.id] = event.job;
            return next;
          case "job.deleted":
            delete next[event.job_id];
            return next;
        }
      });
    });
  }, []);

  // Drop selection if the selected job disappears
  useEffect(() => {
    if (selectedJobId && !jobs[selectedJobId]) setSelectedJobId(null);
  }, [jobs, selectedJobId]);

  const allTags = useMemo(() => {
    const set = new Set<string>();
    Object.values(jobs).forEach((j) => j.tags.forEach((t) => set.add(t)));
    return [...set].sort();
  }, [jobs]);

  const sortedJobs = useMemo(() => {
    let arr = Object.values(jobs).sort((a, b) => a.created_at - b.created_at);
    if (activeFilters.size > 0) {
      arr = arr.filter((j) => j.tags.some((t) => activeFilters.has(t)));
    }
    return arr;
  }, [jobs, activeFilters]);

  const parsedUrls = useMemo(() => parseUrls(urlInput), [urlInput]);
  const parsedTags = useMemo(() => parseTags(tagInput), [tagInput]);

  async function handleSubmit() {
    if (parsedUrls.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      await createJobs(parsedUrls, parsedTags);
      setUrlInput("");
      setTagInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(job: Job) {
    try {
      const removed = await confirmAndDelete(job, (m) => window.confirm(m), deleteJob);
      if (removed && selectedJobId === job.id) setSelectedJobId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleAddTag(job: Job, raw: string) {
    const tag = raw.trim();
    if (!tag || job.tags.includes(tag)) return;
    try {
      await setJobTags(job.id, [...job.tags, tag]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleRemoveTag(job: Job, tag: string) {
    try {
      await setJobTags(job.id, job.tags.filter((t) => t !== tag));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function toggleFilter(tag: string) {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  }

  const selectedJob = selectedJobId ? jobs[selectedJobId] ?? null : null;

  const leftPane = (
    <div className="left-pane">
      <header>
        <h1>YouTube Transcripts</h1>
      </header>

      <section className="submit-section">
        <textarea
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          placeholder={"https://www.youtube.com/watch?v=...\nhttps://youtu.be/..."}
          spellCheck={false}
          rows={3}
        />
        <input
          className="tag-input"
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          placeholder="Optional tags (comma-separated)"
        />
        <div className="row">
          <button
            onClick={handleSubmit}
            disabled={submitting || parsedUrls.length === 0}
          >
            {submitting
              ? "Submitting…"
              : `Submit ${parsedUrls.length || ""} URL${
                  parsedUrls.length === 1 ? "" : "s"
                }`}
          </button>
          <span className="hint">
            {parsedUrls.length === 0
              ? "Awaiting URLs"
              : `${parsedUrls.length} URL${
                  parsedUrls.length === 1 ? "" : "s"
                }${parsedTags.length ? ` · tags: ${parsedTags.join(", ")}` : ""}`}
          </span>
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      {allTags.length > 0 && (
        <section className="filter-section">
          <span className="filter-label">Filter by tag:</span>
          {allTags.map((tag) => (
            <button
              key={tag}
              className={`filter-chip ${activeFilters.has(tag) ? "active" : ""}`}
              onClick={() => toggleFilter(tag)}
            >
              {tag}
            </button>
          ))}
          {activeFilters.size > 0 && (
            <button
              className="filter-clear"
              onClick={() => setActiveFilters(new Set())}
            >
              Clear
            </button>
          )}
        </section>
      )}

      <section className="jobs-section">
        {sortedJobs.length === 0 ? (
          <p style={{ color: "#888" }}>No jobs match.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Submitted</th>
                <th>Video</th>
                <th>Tags</th>
                <th>Stage</th>
                <th>Progress</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedJobs.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  selected={job.id === selectedJobId}
                  onSelect={() => setSelectedJobId(job.id)}
                  onDelete={() => handleDelete(job)}
                  onAddTag={(raw) => handleAddTag(job, raw)}
                  onRemoveTag={(tag) => handleRemoveTag(job, tag)}
                />
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );

  const rightPane = <Viewer job={selectedJob} />;

  return (
    <Splitter
      left={leftPane}
      right={rightPane}
      initialLeftPct={60}
      storageKey="yt-transcripts:split-pct"
    />
  );
}

function JobRow({
  job,
  selected,
  onSelect,
  onDelete,
  onAddTag,
  onRemoveTag,
}: {
  job: Job;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onAddTag: (tag: string) => void;
  onRemoveTag: (tag: string) => void;
}) {
  const [tagDraft, setTagDraft] = useState("");
  const stageClass =
    job.status === "done" ? "stage done" :
    job.status === "failed" ? "stage failed" :
    "stage";

  return (
    <tr className={selected ? "selected" : ""} onClick={onSelect}>
      <td className="date-cell">{formatDate(job.created_at)}</td>
      <td>
        <div className="video-title">{job.title ?? <em>Resolving…</em>}</div>
        <div className="url">{job.url}</div>
      </td>
      <td className="tags-cell" onClick={(e) => e.stopPropagation()}>
        <div className="tag-chips">
          {job.tags.map((tag) => (
            <span key={tag} className="tag-chip">
              {tag}
              <button
                className="tag-remove"
                title="Remove tag"
                onClick={() => onRemoveTag(tag)}
              >
                ×
              </button>
            </span>
          ))}
          <input
            className="tag-add"
            value={tagDraft}
            onChange={(e) => setTagDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === ",") {
                e.preventDefault();
                if (tagDraft.trim()) {
                  onAddTag(tagDraft);
                  setTagDraft("");
                }
              }
            }}
            placeholder="+ tag"
          />
        </div>
      </td>
      <td>
        <span className={stageClass}>{STAGE_LABEL[job.status]}</span>
        <div style={{ fontSize: "0.78rem", color: "#888", marginTop: 4 }}>
          {job.stage_label}
        </div>
        {job.error && <div className="error">{job.error}</div>}
      </td>
      <td>
        <div className="bar">
          <div
            className="bar-fill"
            style={{ width: `${Math.min(100, Math.max(0, job.progress))}%` }}
          />
        </div>
        <div style={{ fontSize: "0.72rem", color: "#888", marginTop: 4 }}>
          {job.progress.toFixed(0)}%
        </div>
      </td>
      <td onClick={(e) => e.stopPropagation()}>
        <div className="actions">
          <button
            onClick={onSelect}
            disabled={!job.summary_path && !job.structured_transcript_path && !job.raw_transcript_path}
          >
            View
          </button>
          <button onClick={onDelete}>Remove</button>
        </div>
      </td>
    </tr>
  );
}

function parseUrls(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0 && /^https?:\/\//i.test(s));
}

function parseTags(text: string): string[] {
  const seen = new Set<string>();
  return text
    .split(/[,\n]+/)
    .map((s) => s.trim())
    .filter((s) => {
      if (!s || seen.has(s)) return false;
      seen.add(s);
      return true;
    });
}

function formatDate(unix: number): string {
  const d = new Date(unix * 1000);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  if (sameDay) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
}
