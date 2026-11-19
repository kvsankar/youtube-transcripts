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

## Job list

| ID | Requirement |
| --- | --- |
| UI-1 | Remove asks for confirmation, naming the video by title (or URL when it has no title). Cancel keeps the job; OK deletes it. Removing a job deletes only its row, not its audio or transcript files. |
| UI-2 | Each video shows a four-step track: Download, Transcribe, Tidy up, Summarise. Steps before the running one are done, the running one fills with its progress, and a failed job marks the step its error names. |
| UI-3 | The status text reads Waiting, "<Verb> <n>%" while a step runs, Ready, "Stopped at <step>" (or Stopped) on failure, and Cancelled. A video with no title reads "Finding the video…" while it is queued or downloading, and "Untitled video" after that. |
| UI-4 | Every colour, type size, weight, radius, shadow and spacing value lives in `frontend/src/tokens.css`. `npm run lint:css` (stylelint) rejects raw values in the other stylesheets, and no element has a `style` attribute; dynamic sizes go through CSS custom properties. |
