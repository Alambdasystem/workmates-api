# Workmates API — Backend

The real Workmates backend: login sessions, admin permissions, private group membership, saved chat, workmate system prompts, job execution, OpenAI Responses integration, tasks, documents, and activity logs. The frontend is in [workmates-core](https://github.com/Alambdasystem/workmates-core).

This service uses real SQLite persistence and makes real OpenAI API calls when configured. No mock server is deployed. Automated tests inject simulated provider responses so permission and cancellation behavior can be tested without API charges.

## Runtime configuration

| Variable | Purpose |
| --- | --- |
| `ADMIN_EMAIL` | Initial admin email; required for an empty database |
| `ADMIN_PASSWORD` | Initial password, at least 14 characters; keep secret |
| `ADMIN_NAME` | Admin display name; defaults to James Hill |
| `OPENAI_API_KEY` | Server-side OpenAI API key |
| `OPENAI_MODEL` | Defaults to `gpt-6-astra`; must support Responses and function calling |
| `TRANSCRIPTION_MODEL` | Defaults to `gpt-transcribe`; used for opt-in microphone recordings |
| `DB_PATH` | SQLite database path; use `/var/data/workmates.db` on the Render persistent disk |
| `COOKIE_SECURE` | `true` in production; `false` only for local HTTP |

`.env.example` contains variable names only. The app reads environment variables and does not automatically load an `.env` file. Never commit secret values.

## Run locally

Python 3.12+:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ADMIN_EMAIL='your-admin-email@example.com'
export ADMIN_NAME='James Hill'
export COOKIE_SECURE=false
export PORT=8001
read -rsp 'Initial admin password (14+ characters): ' ADMIN_PASSWORD
export ADMIN_PASSWORD
read -rsp 'OpenAI API key: ' OPENAI_API_KEY
export OPENAI_API_KEY
python server.py
```

Run the frontend separately on port 8000, pointing `WORKMATES_API_URL` at http://127.0.0.1:8001.

## Render deployment

The included `render.yaml` defines one backend web service on a `0.5c-512mb` compute plan with a 1 GB persistent disk. These are paid resources. The database must be on this disk; Render's normal filesystem is ephemeral.

1. Create a Render Blueprint from this repository.
2. Set `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `OPENAI_API_KEY` in its secret prompts.
3. Deploy and verify `/healthz`.
4. Deploy the frontend repository and set its `WORKMATES_API_URL` to the backend's HTTPS origin.
5. Sign in through the frontend, create a group, configure/enable its workmate, and send an `@workmate` request.

Start command:

```bash
python -m waitress --call --listen=0.0.0.0:$PORT --threads=8 --max-request-body-size=8388608 server:create_app
```

Use exactly one backend instance. Waitress serves HTTP requests in eight threads, and the application runs one AI job thread. This first implementation uses a single SQLite database and an in-process job worker. Scaling requires a shared database and a separate worker/queue. Back up SQLite using its backup API so WAL transactions are included.

`ADMIN_PASSWORD` initializes an empty database only; it is not a password-reset mechanism. Use Change password in the frontend. There is no email password-recovery flow in this version.

## Workmate behavior

Each group has one administrator-configured workmate. Name, system prompt, enabled state, mention/all-message mode, and enabled tools are independent per group. Only the administrator can change them.

Enabled tools:

- `create_task`: save a task in the current group, with an assignee label.
- `save_document`: save a shared text document in the current group.
- `web_search`: research current information with OpenAI web search; citations are saved and shown as clickable sources.

Tasks do not notify assignees. The tool registry now includes hosted web search, code execution, image generation, Canvas document operations and scoped Google Drive operations. Email and arbitrary shell/computer access are not implemented. Each tool must be enabled by the administrator; a system prompt cannot grant tools.

The agent receives the latest 60 messages through the triggering message, 30 recent task summaries, and 100 document IDs, titles and versions. It does not automatically retrieve the full historical archive or saved document bodies. History itself remains stored across restarts.

Turning a workmate off or changing its settings cancels pending work. Tools check the current revision before committing, and late replies are discarded. Already-dispatched OpenAI requests may still incur usage charges. Previously saved actions remain. A server restart marks in-progress work interrupted rather than replaying potentially completed actions.

## API and access

`openapi.json` describes every backend route. `examples/client.py` provides a direct API client using cookies and CSRF, with a read-only group-listing CLI. Direct browser integrations must use the same origin; the frontend service provides the proxy for this.

- Only the admin creates groups, manages invitations/members, and changes workmate settings.
- Members see only their groups. The admin sees every group.
- Invitations are email-bound, single-use, and expire in seven days. The app returns invitation links for manual sharing; it does not send emails.
- Login uses password hashes and expiring HttpOnly/Secure/SameSite cookies. Authenticated writes require `X-CSRF-Token` from `/api/me`.
- Send messages with a stable `request_id`; reuse it only for retries of the same message. Duplicate sends are not reprocessed.
- `/api/rooms/{room_id}` returns recent messages, jobs, documents, activity, members, and tasks. Polling is used instead of token streaming.
- Group membership and tools are enforced server-side. The OpenAI key is never sent to the frontend.

Five pending AI requests per group, five model turns per job, and login/message throttles provide basic bounds. Configure project spending limits in OpenAI for billing control. Relevant group content is sent to OpenAI when invoked. This version has no enterprise SSO, end-to-end encryption, retention policy engine, or managed recovery flow.

## Verification

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Tests cover authorization, invitations, room isolation, persistence, tool execution, denied tools, duplicate sends, workmate cancellation, CSRF, missing-key errors, password changes, and OpenAPI route/response parity. Live OpenAI and Render verification must still be completed after deployment.

## Voice and autopilot (v0.2)

The Talk button requests microphone access only when clicked. Tap Stop to transcribe through the authenticated same-origin backend. Audio goes to OpenAI for transcription and is not saved in the Workmates database. The transcript is inserted into your draft for review; it is never sent to the group automatically. Recordings stop after 90 seconds and when leaving the group or hiding the tab. Browser microphone permissions and HTTPS are required.

`POST /api/rooms/{room_id}/transcribe` accepts raw `audio/webm`, `audio/mp4`, `audio/wav`, or `audio/mpeg` up to 8 MiB. It requires membership, the session cookie and CSRF, and has a per-user rate limit. JSON requests remain limited to 64 KiB.

Mention mode recognizes the configured workmate name as a whole word, case-insensitively, with or without `@`. Autopilot (`mode: all`) follows new group messages, uses an admin-defined `goal`, combines message bursts with a four-second debounce, and spaces updates by at least 30 seconds from the previous request. It does not record background audio or continue working without new messages. Up to 30 automatic requests per group per hour are allowed; explicit named requests remain available. It can choose to stay silent. Only human messages trigger jobs, preventing agent self-loops.

The right-side admin controls turn autopilot and individual tools on or off. Pause cancels pending work; an already-dispatched provider request can still incur charges. Existing history is preserved by additive SQLite migrations. Model IDs are visible in the workspace and `/api/me`. This app uses the OpenAI API independently from a ChatGPT subscription and exposes only the integrations implemented here.

The backend uses Waitress to avoid a forking server startup path. SQLite WAL mode is established once during initialization, and `/healthz` verifies the application and database before Render routes traffic.


## Documents Canvas and Drive v03

Group documents use Markdown with headings, bold text, lists, tables and fenced code. They export through authenticated endpoints as real Word DOCX, PDF, Markdown, text or HTML. Canvas provides an editor, formatted preview, version history, conflict detection, separate branches, and an assistant revision request. The UI retains drafts until explicit Save; it never silently replaces them with an AI edit. AI revisions must read the latest version first. Imports support DOCX, text PDFs, MD, TXT, CSV and JSON, at most 8 MB and 40000 extracted characters; scanned PDFs need OCR outside this version. Importing preserves text and tables, not the entire source layout.

Hosted code execution uses an OpenAI sandbox, never the application host. Generated file citations are copied to the persistent database before exposing authenticated download links. Generated PNG images are also persisted. Downloads are capped at 8 MB each and generated files at 64 MB per group. Code and image tools carry separate provider charges and are opt-in for existing groups. New group defaults include document editing and web research. The admin's Enable all available tools control exposes every implemented tool; this is not automatic access to every ChatGPT connector, Canvas product feature, or computer tool.

Google setup: enable Drive API in a Google Cloud project, configure the OAuth consent screen (and test users while in testing), and create a Web application OAuth client. Add `https://workmates-core.onrender.com/api/integrations/google/callback` as an exact authorized redirect URI. Enter its client ID and secret in Drive > Manage Drive connections. Alternatively set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `PUBLIC_APP_URL` on the backend. Then connect each Google account through Google's consent screen. Credentials are never returned to the browser or model; refresh tokens and stored client settings are encrypted using a generated key next to the database. **Back up both the SQLite database and `.integration-key`; loss of the key requires reconnecting Google accounts.** Do not commit either file.

Drive consent requests read/write Drive scope to support existing personal and shared folders. The application enforces selected folder ancestry on every group operation. Only administrators attach or remove accounts/folders; every member of the target group can work inside an attached folder using the connected account. There may be several accounts and several folders per group. Browse supports pagination and nested folders; import copies readable content into Canvas; save creates a NEW formatted native Google Doc; branch creates a new subfolder. No overwrite, sharing change, file deletion or new Shared Drive creation is exposed. Google may require OAuth verification for a public app using this scope. Testing status may limit token duration. ChatGPT's Google connector authorization is separate and cannot be reused here.

OAuth uses PKCE, a ten-minute single-use state bound to a live admin session, server-side code exchange, and a fixed relative callback result. Disconnect removes the encrypted connection and all its mounts and cancels pending work. Already dispatched provider actions cannot be recalled. The Google HTTP transport is injected in tests; live Google operations require configured client credentials and account consent.

Verification includes real DOCX/PDF parsing, export/import roundtrips, edit conflict protection, branch preservation, unauthenticated and cross-group download denial, token encryption, OAuth state replay rejection, Drive ancestry restriction, shared-drive flags, and connection removal. Use `python -m unittest discover -s tests -v`.
