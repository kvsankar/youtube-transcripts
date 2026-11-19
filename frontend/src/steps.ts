import type { Job, JobStatus } from "./types";

export type StepState = "todo" | "active" | "done" | "failed";

export interface Step {
  status: JobStatus;
  label: string;
  verb: string;
  errorPrefix: string;
}

/** The pipeline's four steps, in the order the backend runs them. */
export const STEPS: readonly Step[] = [
  { status: "downloading", label: "Download", verb: "Downloading", errorPrefix: "Download failed" },
  { status: "transcribing", label: "Transcribe", verb: "Transcribing", errorPrefix: "Transcription failed" },
  { status: "structuring", label: "Tidy up", verb: "Tidying up", errorPrefix: "Structuring failed" },
  { status: "summarizing", label: "Summarise", verb: "Summarising", errorPrefix: "Summarization failed" },
];

type JobProgress = Pick<Job, "status" | "progress" | "error">;

function failedIndex(job: JobProgress): number {
  return STEPS.findIndex((s) => job.error?.startsWith(s.errorPrefix));
}

export function stepStates(job: JobProgress): { label: string; state: StepState; progress: number }[] {
  const running = STEPS.findIndex((s) => s.status === job.status);
  const failed = job.status === "failed" ? failedIndex(job) : -1;
  return STEPS.map((s, i) => {
    let state: StepState = "todo";
    if (job.status === "done") state = "done";
    else if (failed >= 0) state = i < failed ? "done" : i === failed ? "failed" : "todo";
    else if (running >= 0) state = i < running ? "done" : i === running ? "active" : "todo";
    return { label: s.label, state, progress: state === "active" ? job.progress : 0 };
  });
}

export function statusText(job: JobProgress): string {
  switch (job.status) {
    case "queued":
      return "Waiting";
    case "done":
      return "Ready";
    case "cancelled":
      return "Cancelled";
    case "failed": {
      const i = failedIndex(job);
      return i >= 0 ? `Stopped at ${STEPS[i].label}` : "Stopped";
    }
    default: {
      const step = STEPS.find((s) => s.status === job.status);
      return `${step?.verb ?? "Working"} ${Math.round(job.progress)}%`;
    }
  }
}

/** The video's title, or what to show while it is unknown. */
export function displayTitle(job: Pick<Job, "status" | "title">): string {
  if (job.title) return job.title;
  return job.status === "queued" || job.status === "downloading" ? "Finding the video…" : "Untitled video";
}
