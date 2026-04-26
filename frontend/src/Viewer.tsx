import { useEffect, useMemo, useState } from "react";
import { marked } from "marked";
import { fetchTranscript } from "./api";
import type { Job, TranscriptKind, ViewerMode } from "./types";

const KIND_LABEL: Record<TranscriptKind, string> = {
  summary: "Summary",
  structured: "Structured",
  raw: "Raw",
};

export function Viewer({
  job,
  initialKind = "summary",
}: {
  job: Job | null;
  initialKind?: TranscriptKind;
}) {
  const [kind, setKind] = useState<TranscriptKind>(initialKind);
  const [mode, setMode] = useState<ViewerMode>("html");
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset selected kind when switching jobs, preferring whichever output
  // is actually available.
  useEffect(() => {
    if (!job) return;
    if (job.summary_path) setKind("summary");
    else if (job.structured_transcript_path) setKind("structured");
    else if (job.raw_transcript_path) setKind("raw");
  }, [job?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const available: Record<TranscriptKind, boolean> = useMemo(() => ({
    summary: !!job?.summary_path,
    structured: !!job?.structured_transcript_path,
    raw: !!job?.raw_transcript_path,
  }), [job]);

  useEffect(() => {
    let cancelled = false;
    if (!job) {
      setText(null);
      return;
    }
    if (!available[kind]) {
      setText(null);
      return;
    }
    setLoading(true);
    setError(null);
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
  }, [job?.id, kind, available, job]);

  const renderedHtml = useMemo(() => {
    if (text == null) return "";
    if (kind === "raw") return ""; // raw is plain text, no markdown rendering
    try {
      return marked.parse(text, { async: false }) as string;
    } catch {
      return text;
    }
  }, [text, kind]);

  if (!job) {
    return (
      <div className="viewer viewer-empty">
        <p>Select a job to view its summary, structured transcript, or raw transcript.</p>
      </div>
    );
  }

  return (
    <div className="viewer">
      <div className="viewer-header">
        <div className="viewer-title">
          <strong>{job.title ?? job.url}</strong>
        </div>
        <div className="viewer-tabs">
          {(["summary", "structured", "raw"] as TranscriptKind[]).map((k) => (
            <button
              key={k}
              className={`viewer-tab ${kind === k ? "active" : ""}`}
              disabled={!available[k]}
              onClick={() => setKind(k)}
            >
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>
        {kind !== "raw" && (
          <div className="viewer-mode-toggle">
            <button
              className={mode === "html" ? "active" : ""}
              onClick={() => setMode("html")}
            >
              HTML
            </button>
            <button
              className={mode === "markdown" ? "active" : ""}
              onClick={() => setMode("markdown")}
            >
              Markdown
            </button>
          </div>
        )}
      </div>

      <div className="viewer-body">
        {loading && <p style={{ color: "#888" }}>Loading…</p>}
        {error && <p className="error">Error: {error}</p>}
        {!loading && !error && text == null && (
          <p style={{ color: "#888" }}>This output isn't available yet for this job.</p>
        )}
        {!loading && !error && text != null && kind === "raw" && (
          <pre className="viewer-raw">{text}</pre>
        )}
        {!loading && !error && text != null && kind !== "raw" && mode === "markdown" && (
          <pre className="viewer-raw">{text}</pre>
        )}
        {!loading && !error && text != null && kind !== "raw" && mode === "html" && (
          <div
            className="viewer-rendered"
            dangerouslySetInnerHTML={{ __html: renderedHtml }}
          />
        )}
      </div>
    </div>
  );
}
