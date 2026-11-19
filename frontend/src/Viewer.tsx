import { useEffect, useMemo, useState } from "react";
import { marked } from "marked";
import { fetchTranscript } from "./api";
import { formatDate } from "./hooks";
import { StepTrack } from "./StepTrack";
import { displayTitle, statusText } from "./steps";
import type { Job, TranscriptKind } from "./types";

const TABS: { kind: TranscriptKind; label: string }[] = [
  { kind: "summary", label: "Digest" },
  { kind: "structured", label: "Transcript" },
  { kind: "raw", label: "Raw text" },
];

function availableKinds(job: Job): Record<TranscriptKind, boolean> {
  return {
    summary: !!job.summary_path,
    structured: !!job.structured_transcript_path,
    raw: !!job.raw_transcript_path,
  };
}

export function Viewer({
  job,
  onBack,
  onRemove,
  onAddTag,
  onRemoveTag,
}: {
  job: Job | null;
  onBack: () => void;
  onRemove: (job: Job) => void;
  onAddTag: (job: Job, tag: string) => void;
  onRemoveTag: (job: Job, tag: string) => void;
}) {
  const [kind, setKind] = useState<TranscriptKind>("summary");
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [tagDraft, setTagDraft] = useState("");

  const available = useMemo(
    () => (job ? availableKinds(job) : { summary: false, structured: false, raw: false }),
    [job],
  );

  // On switching videos, open the most finished output that exists.
  useEffect(() => {
    if (!job) return;
    const a = availableKinds(job);
    setKind(a.summary ? "summary" : a.structured ? "structured" : a.raw ? "raw" : "summary");
    setTagDraft("");
  }, [job?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false;
    setCopied(false);
    setText(null);
    setError(null);
    if (!job || !available[kind]) return;
    setLoading(true);
    fetchTranscript(job.id, kind)
      .then((t) => {
        if (!cancelled) setText(t);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [job?.id, kind, available[kind]]); // eslint-disable-line react-hooks/exhaustive-deps

  const html = useMemo(() => {
    if (text == null || kind === "raw") return "";
    try {
      return marked.parse(text, { async: false }) as string;
    } catch {
      return "";
    }
  }, [text, kind]);

  if (!job) {
    return (
      <div className="reader-empty">
        <p>Choose a video to read its digest, or paste a link to add one.</p>
      </div>
    );
  }

  const current = job;
  const tabLabel = TABS.find((t) => t.kind === kind)!.label.toLowerCase();
  const running = !["done", "failed", "cancelled"].includes(current.status);
  const hasOutput = available.summary || available.structured || available.raw;

  async function copy() {
    if (text == null) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  function addTag() {
    const tag = tagDraft.trim();
    if (tag && !current.tags.includes(tag)) onAddTag(current, tag);
    setTagDraft("");
  }

  return (
    <article className="reader-inner">
      <button className="btn btn-ghost reader-back" onClick={onBack}>
        Back to videos
      </button>

      <h1 className="reader-title">{displayTitle(current)}</h1>

      <div className="reader-meta">
        <span className={current.status === "failed" ? "status-danger" : undefined}>{statusText(current)}</span>
        <span>Added {formatDate(current.created_at)}</span>
        <a className="link" href={current.url} target="_blank" rel="noreferrer">
          Open on YouTube
        </a>
      </div>

      <div className="tags" role="group" aria-label="Tags">
        {current.tags.map((tag) => (
          <span key={tag} className="tag">
            {tag}
            <button
              className="tag-remove"
              aria-label={`Remove tag ${tag}`}
              onClick={() => onRemoveTag(current, tag)}
            >
              ×
            </button>
          </span>
        ))}
        <label className="visually-hidden" htmlFor="tag-draft">
          Add a tag
        </label>
        <input
          id="tag-draft"
          className="input tag-input"
          value={tagDraft}
          placeholder="Add tag"
          size={8}
          onChange={(e) => setTagDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              addTag();
            }
          }}
          onBlur={addTag}
        />
      </div>

      {current.status === "failed" && (
        <div className="notice notice-danger" role="status">
          <p>
            <strong>{statusText(current)}.</strong> To try again, remove this video and add its link again.
          </p>
          {current.error && <p className="notice-detail">{current.error}</p>}
        </div>
      )}

      {running && (
        <div className="notice">
          <StepTrack job={current} large />
          <p className="hint">The digest appears here when it is ready. You can close this page meanwhile.</p>
        </div>
      )}

      <div className={hasOutput ? "reader-tools reader-tools-tabs" : "reader-tools"}>
        {hasOutput && (
        <div className="tabs" role="tablist" aria-label="Output">
          {TABS.map((t) => (
            <button
              key={t.kind}
              role="tab"
              id={`tab-${t.kind}`}
              aria-controls="reader-panel"
              aria-selected={kind === t.kind}
              className="tab"
              disabled={!available[t.kind]}
              onClick={() => setKind(t.kind)}
            >
              {t.label}
            </button>
          ))}
        </div>
        )}
        <div className="tools">
          {hasOutput && (
            <button className="btn btn-ghost btn-sm" onClick={copy} disabled={text == null}>
              {copied ? "Copied" : kind === "raw" ? "Copy text" : "Copy as Markdown"}
            </button>
          )}
          <button className="btn btn-danger btn-sm" onClick={() => onRemove(current)}>
            Remove
          </button>
        </div>
      </div>
      <span className="visually-hidden" aria-live="polite">
        {copied ? `Copied the ${tabLabel}` : ""}
      </span>

      <div id="reader-panel" role={hasOutput ? "tabpanel" : undefined} aria-labelledby={hasOutput ? `tab-${kind}` : undefined}>
        {!hasOutput && current.status === "cancelled" && <p className="hint">This video was cancelled before any text was made.</p>}
        {loading && text == null && <p className="hint">Loading the {tabLabel}…</p>}
        {error && (
          <p className="error-text">
            Could not load the {tabLabel}: {error}
          </p>
        )}
        {text != null && kind === "raw" && <pre className="plain">{text}</pre>}
        {text != null && kind !== "raw" && <div className="prose" dangerouslySetInnerHTML={{ __html: html }} />}
      </div>
    </article>
  );
}
