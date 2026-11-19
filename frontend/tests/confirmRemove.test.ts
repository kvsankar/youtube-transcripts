// UI-1 in docs/specs.md: Remove asks for confirmation before it deletes a job.
// Run: npm test (node --test with type stripping; no extra packages).
import { test } from "node:test";
import assert from "node:assert/strict";
import { confirmAndDelete, removeConfirmText } from "../src/confirmRemove.ts";

const job = { id: "j1", url: "https://www.youtube.com/watch?v=abc", title: "A talk" };

test("the question names the video by title", () => {
  assert.match(removeConfirmText(job), /A talk/);
});

test("the question falls back to the URL when there is no title", () => {
  assert.match(removeConfirmText({ ...job, title: null }), /watch\?v=abc/);
});

test("cancel does not delete", async () => {
  const deleted: string[] = [];
  const done = await confirmAndDelete(job, () => false, async (id) => { deleted.push(id); });
  assert.equal(done, false);
  assert.deepEqual(deleted, []);
});

test("OK deletes the job", async () => {
  const deleted: string[] = [];
  const done = await confirmAndDelete(job, () => true, async (id) => { deleted.push(id); });
  assert.equal(done, true);
  assert.deepEqual(deleted, ["j1"]);
});
