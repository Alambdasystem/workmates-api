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

Tasks do not notify assignees. The agent has web research when enabled, but no email, code execution, image generation, or other external integrations. Those require additional server-side tools; a system prompt alone cannot grant them.

The agent receives the latest 60 messages through the triggering message, 30 recent task summaries, and 30 document titles. It does not automatically retrieve the full historical archive or saved document bodies. History itself remains stored across restarts.

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
