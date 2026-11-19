import { useEffect, useMemo, useRef, useState } from "react";
import { createJobs, deleteJob, setJobTags, subscribeEvents } from "./api";
import { confirmAndDelete } from "./confirmRemove";
import { formatDate, useCssVar, useMediaQuery } from "./hooks";
import { StepTrack } from "./StepTrack";
import { displayTitle, statusText } from "./steps";
import { Viewer } from "./Viewer";
import type { Job } from "./types";

const SPLIT_KEY = "yt-transcripts:library-pct";
const SPLIT_DEFAULT = 35;
const SPLIT_MIN = 20;
const SPLIT_MAX = 70;

export function App() {
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filters, setFilters] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const narrow = useMediaQuery("(width <= 760px)");

  useEffect(
    () =>
      subscribeEvents((event) => {
        setJobs((prev) => {
          switch (event.type) {
            case "snapshot":
              return Object.fromEntries(event.jobs.map((j) => [j.id, j]));
            case "job.created":
            case "job.updated":
              return { ...prev, [event.job.id]: event.job };
            case "job.deleted": {
              const next = { ...prev };
              delete next[event.job_id];
              return next;
            }
          }
        });
      }),
    [],
  );

  useEffect(() => {
    if (selectedId && !jobs[selectedId]) setSelectedId(null);
  }, [jobs, selectedId]);

  const allTags = useMemo(() => {
    const set = new Set<string>();
    Object.values(jobs).forEach((j) => j.tags.forEach((t) => set.add(t)));
    return [...set].sort();
  }, [jobs]);

  // Newest first: the video you just added is at the top.
  const visible = useMemo(() => {
    const list = Object.values(jobs).sort((a, b) => b.created_at - a.created_at);
    return filters.size ? list.filter((j) => j.tags.some((t) => filters.has(t))) : list;
  }, [jobs, filters]);

  const [split, setSplit] = useState(() => {
    try {
      const v = parseFloat(localStorage.getItem(SPLIT_KEY) ?? "");
      return Number.isFinite(v) ? clamp(v) : SPLIT_DEFAULT;
    } catch {
      return SPLIT_DEFAULT;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(SPLIT_KEY, String(split));
    } catch {
      /* private window: keep the split for this visit only */
    }
  }, [split]);
  const appRef = useCssVar<HTMLDivElement>("--split", `${split}%`);

  async function run(action: () => Promise<unknown>): Promise<boolean> {
    try {
      setError(null);
      await action();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return false;
    }
  }

  const selected = selectedId ? jobs[selectedId] ?? null : null;

  return (
    <div className="app" ref={appRef} data-view={narrow && selected ? "reader" : "list"}>
      <aside className="library" aria-label="Videos">
        <h1 className="brand">YouTube Transcripts</h1>
        <AddForm onAdd={(urls, tags) => run(() => createJobs(urls, tags))} />
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}

        {allTags.length > 0 && (
          <div className="filters" role="group" aria-label="Show only videos tagged">
            {allTags.map((tag) => (
              <button
                key={tag}
                className="chip"
                aria-pressed={filters.has(tag)}
                onClick={() =>
                  setFilters((prev) => {
                    const next = new Set(prev);
                    if (next.has(tag)) next.delete(tag);
                    else next.add(tag);
                    return next;
                  })
                }
              >
                {tag}
              </button>
            ))}
            {filters.size > 0 && (
              <button className="btn btn-ghost btn-sm" onClick={() => setFilters(new Set())}>
                Show all
              </button>
            )}
          </div>
        )}

        {visible.length === 0 ? (
          <p className="empty-list">
            {filters.size ? "No video has these tags." : "No videos yet. Paste a YouTube link above to start."}
          </p>
        ) : (
          <ul className="video-list">
            {visible.map((job) => (
              <li key={job.id}>
                <button
                  className="video"
                  aria-current={job.id === selectedId}
                  onClick={() => setSelectedId(job.id)}
                >
                  <span className="video-title">{displayTitle(job)}</span>
                  <span className="video-meta">
                    <StepTrack job={job} />
                    <span className={job.status === "failed" ? "status-danger" : undefined}>{statusText(job)}</span>
                    <span className="video-date">{formatDate(job.created_at)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      <Divider split={split} onChange={setSplit} />

      <main className="reader">
        <Viewer
          job={selected}
          onBack={() => setSelectedId(null)}
          onRemove={(job) => run(() => confirmAndDelete(job, (m) => window.confirm(m), deleteJob))}
          onAddTag={(job, tag) => run(() => setJobTags(job.id, [...job.tags, tag]))}
          onRemoveTag={(job, tag) => run(() => setJobTags(job.id, job.tags.filter((t) => t !== tag)))}
        />
      </main>
    </div>
  );
}

function AddForm({ onAdd }: { onAdd: (urls: string[], tags: string[]) => Promise<boolean> }) {
  const [links, setLinks] = useState("");
  const [tags, setTags] = useState("");
  const [busy, setBusy] = useState(false);
  const urls = useMemo(() => parseUrls(links), [links]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!urls.length) return;
    setBusy(true);
    const added = await onAdd(urls, parseTags(tags));
    setBusy(false);
    if (added) {
      setLinks("");
      setTags("");
    }
  }

  return (
    <form className="add" onSubmit={submit}>
      <div className="field">
        <label className="field-label" htmlFor="links">
          Add videos
        </label>
        <textarea
          id="links"
          className="input"
          rows={2}
          spellCheck={false}
          value={links}
          placeholder="Paste one or more YouTube links"
          onChange={(e) => setLinks(e.target.value)}
        />
      </div>
      <label className="visually-hidden" htmlFor="new-tags">
        Tags for these videos
      </label>
      <input
        id="new-tags"
        className="input"
        value={tags}
        placeholder="Tags, separated by commas (optional)"
        onChange={(e) => setTags(e.target.value)}
      />
      <div className="add-row">
        <button className="btn btn-primary" type="submit" disabled={busy || urls.length === 0}>
          {busy ? "Adding…" : urls.length > 1 ? `Add ${urls.length} videos` : "Add video"}
        </button>
      </div>
    </form>
  );
}

function Divider({ split, onChange }: { split: number; onChange: (pct: number) => void }) {
  const dragging = useRef(false);

  function move(e: React.PointerEvent<HTMLDivElement>) {
    if (!dragging.current) return;
    const frame = e.currentTarget.parentElement!.getBoundingClientRect();
    onChange(clamp(((e.clientX - frame.left) / frame.width) * 100));
  }

  return (
    <div
      className="divider"
      role="separator"
      tabIndex={0}
      aria-label="Resize the video list"
      aria-orientation="vertical"
      aria-valuemin={SPLIT_MIN}
      aria-valuemax={SPLIT_MAX}
      aria-valuenow={Math.round(split)}
      onPointerDown={(e) => {
        dragging.current = true;
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={move}
      onPointerUp={() => (dragging.current = false)}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") onChange(clamp(split - 5));
        if (e.key === "ArrowRight") onChange(clamp(split + 5));
      }}
    />
  );
}

function clamp(pct: number): number {
  return Math.max(SPLIT_MIN, Math.min(SPLIT_MAX, pct));
}

function parseUrls(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter((s) => /^https?:\/\//i.test(s));
}

function parseTags(text: string): string[] {
  return [...new Set(text.split(/[,\n]+/).map((s) => s.trim()).filter(Boolean))];
}
