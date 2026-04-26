import type { Job, ServerEvent } from "./types";

export async function createJobs(
  urls: string[],
  tags: string[] = []
): Promise<Job[]> {
  const res = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls, tags }),
  });
  if (!res.ok) {
    throw new Error(`createJobs failed: ${res.status} ${await res.text()}`);
  }
  const data = await res.json();
  return data.jobs as Job[];
}

export async function deleteJob(jobId: string): Promise<void> {
  const res = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) {
    throw new Error(`deleteJob failed: ${res.status}`);
  }
}

export async function setJobTags(jobId: string, tags: string[]): Promise<Job> {
  const res = await fetch(`/api/jobs/${jobId}/tags`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tags }),
  });
  if (!res.ok) {
    throw new Error(`setJobTags failed: ${res.status}`);
  }
  return (await res.json()) as Job;
}

export async function fetchTranscript(
  jobId: string,
  kind: "raw" | "structured" | "summary"
): Promise<string> {
  const res = await fetch(`/api/jobs/${jobId}/${kind}`);
  if (!res.ok) {
    throw new Error(`fetchTranscript(${kind}) failed: ${res.status}`);
  }
  return await res.text();
}

export function subscribeEvents(onEvent: (e: ServerEvent) => void): () => void {
  const es = new EventSource("/api/events");
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as ServerEvent);
    } catch (err) {
      console.error("Failed to parse SSE event", err, msg.data);
    }
  };
  es.onerror = (err) => {
    console.warn("SSE error (browser will auto-reconnect)", err);
  };
  return () => es.close();
}
