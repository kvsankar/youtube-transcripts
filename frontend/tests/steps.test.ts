// UI-2 and UI-3 in docs/specs.md: the four-step track and the status text.
import { test } from "node:test";
import assert from "node:assert/strict";
import { STEPS, displayTitle, stepStates, statusText } from "../src/steps.ts";

const job = (status: string, progress = 0, error: string | null = null) =>
  ({ status, progress, error }) as Parameters<typeof stepStates>[0];

test("the track has four steps in pipeline order", () => {
  assert.deepEqual(STEPS.map((s) => s.label), ["Download", "Transcribe", "Tidy up", "Summarise"]);
});

test("a queued job has no step started", () => {
  assert.deepEqual(stepStates(job("queued")).map((s) => s.state), ["todo", "todo", "todo", "todo"]);
  assert.equal(statusText(job("queued")), "Waiting");
});

test("the running step is active with its progress; earlier steps are done", () => {
  const s = stepStates(job("transcribing", 42.4));
  assert.deepEqual(s.map((x) => x.state), ["done", "active", "todo", "todo"]);
  assert.equal(s[1].progress, 42.4);
  assert.equal(statusText(job("transcribing", 42.4)), "Transcribing 42%");
});

test("a finished job has every step done and reads Ready", () => {
  assert.deepEqual(stepStates(job("done", 100)).map((s) => s.state), ["done", "done", "done", "done"]);
  assert.equal(statusText(job("done", 100)), "Ready");
});

test("a failed job marks the step named in its error", () => {
  const failed = job("failed", 0, "Transcription failed: out of memory");
  assert.deepEqual(stepStates(failed).map((s) => s.state), ["done", "failed", "todo", "todo"]);
  assert.equal(statusText(failed), "Stopped at Transcribe");
});

test("a failed download marks the first step", () => {
  const failed = job("failed", 0, "Download failed: ERROR: HTTP Error 403: Forbidden");
  assert.deepEqual(stepStates(failed).map((s) => s.state), ["failed", "todo", "todo", "todo"]);
  assert.equal(statusText(failed), "Stopped at Download");
});

test("a failed job with an unknown error still reads as stopped", () => {
  assert.equal(statusText(job("failed", 0, "something else")), "Stopped");
});

test("a cancelled job reads Cancelled", () => {
  assert.equal(statusText(job("cancelled")), "Cancelled");
});

test("the title falls back by state when the video has none", () => {
  const t = (status: string, title: string | null) => displayTitle({ status, title } as Parameters<typeof displayTitle>[0]);
  assert.equal(t("done", "A talk"), "A talk");
  assert.equal(t("queued", null), "Finding the video…");
  assert.equal(t("downloading", null), "Finding the video…");
  assert.equal(t("failed", null), "Untitled video");
});
