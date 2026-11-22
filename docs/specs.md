# Specification

This document states what the application must do when it runs as a
service. Each requirement has an ID; tests in `backend/tests/` name the ID
they check.

## Configuration

| ID | Requirement |
| --- | --- |
| CFG-1 | When `YT_TRANSCRIPTS_DATA_DIR` is set, the backend keeps all runtime data (`audio/`, `transcripts/`, `jobs.db`) in that folder and creates the folders it needs. When it is not set, the folder is `data/` at the repository root. |
| CFG-2 | When `YT_TRANSCRIPTS_WHISPER_MODEL` is set, the transcriber loads that faster-whisper model. When it is not set, it loads `medium`. |

## Serving the frontend

| ID | Requirement |
| --- | --- |
| WEB-1 | When the built frontend exists (`frontend/dist`, or the folder in `YT_TRANSCRIPTS_FRONTEND_DIST`), the backend serves it at `/`, with `index.html` for `/`. |
| WEB-2 | The `/api` routes answer as before when the frontend is served. |
| WEB-3 | When the built frontend does not exist, the backend serves only `/api`, as in development with the Vite dev server. |

## Downloading

| ID | Requirement |
| --- | --- |
| DL-1 | Every yt-dlp call (the metadata probe and the download) enables the Deno and Node JavaScript runtimes, and the backend installs the EJS challenge scripts (`yt-dlp[default]`), so yt-dlp can solve YouTube's JavaScript challenges. Without them YouTube answers the audio download with HTTP 403. |

## Transcribing

| ID | Requirement |
| --- | --- |
| TR-1 | The transcriber decodes the audio with ffmpeg to 16 kHz mono samples in a temporary file and reads them from that file, so the decoded audio is not held in memory. |
| TR-2 | The transcriber gives Whisper the audio in parts of at most 10 minutes, so its memory use does not grow with the length of the video. Each cut is at the quietest half second in the 30 seconds before the 10-minute limit, so a cut seldom falls inside a word. The parts cover the audio in order, without gaps or overlap. |
| TR-3 | The raw transcript joins the text of the parts in order. Progress runs over the whole audio. When the language is `auto`, the language detected in the first part is used for the other parts. |

## Job list

| ID | Requirement |
| --- | --- |
| UI-1 | Remove asks for confirmation, naming the video by title (or URL when it has no title). Cancel keeps the job; OK deletes it. Removing a job deletes only its row, not its audio or transcript files. |
| UI-2 | Each video shows a four-step track: Download, Transcribe, Tidy up, Summarise. Steps before the running one are done, the running one fills with its progress, and a failed job marks the step its error names. |
| UI-3 | The status text reads Waiting, "<Verb> <n>%" while a step runs, Ready, "Stopped at <step>" (or Stopped) on failure, and Cancelled. A video with no title reads "Finding the video…" while it is queued or downloading, and "Untitled video" after that. |
| UI-4 | Every colour, type size, weight, radius, shadow and spacing value lives in `frontend/src/tokens.css`. `npm run lint:css` (stylelint) rejects raw values in the other stylesheets, and no element has a `style` attribute; dynamic sizes go through CSS custom properties. |

## Restarts

| ID | Requirement |
| --- | --- |
| JOB-1 | When the backend starts and finds a job that was running when the process stopped (a crash, an out-of-memory kill or a restart), it puts the job back in the queue and runs it again. The steps whose output files exist are skipped. Jobs that were waiting stay in the queue. |
| JOB-2 | The backend puts an interrupted job back in the queue once. If the job is interrupted again, it is marked failed, and its error names the step (for example "Transcription failed: …") and says to submit the URL again. Submitting the URL of a failed job queues it with a new allowance of one restart. |
