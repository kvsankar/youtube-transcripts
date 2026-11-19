export type JobStatus =
  | "queued"
  | "downloading"
  | "transcribing"
  | "structuring"
  | "summarizing"
  | "done"
  | "failed"
  | "cancelled";

export interface Job {
  id: string;
  url: string;
  status: JobStatus;
  progress: number;
  stage_label: string;
  title: string | null;
  audio_path: string | null;
  raw_transcript_path: string | null;
  structured_transcript_path: string | null;
  summary_path: string | null;
  error: string | null;
  created_at: number;
  updated_at: number;
  tags: string[];
}

export type ServerEvent =
  | { type: "snapshot"; jobs: Job[] }
  | { type: "job.created"; job: Job }
  | { type: "job.updated"; job: Job }
  | { type: "job.deleted"; job_id: string };

export type TranscriptKind = "raw" | "structured" | "summary";
