import type { Job } from "./types";

type JobRef = Pick<Job, "id" | "url" | "title">;

export function removeConfirmText(job: JobRef): string {
  return `Remove "${job.title || job.url}" from the list?`;
}

/** Ask first; delete only when the user confirms. Returns true when deleted. */
export async function confirmAndDelete(
  job: JobRef,
  confirm: (message: string) => boolean,
  remove: (jobId: string) => Promise<void>,
): Promise<boolean> {
  if (!confirm(removeConfirmText(job))) return false;
  await remove(job.id);
  return true;
}
