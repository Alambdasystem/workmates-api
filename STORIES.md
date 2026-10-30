# Reusable image workflows

## S1 Saved images stay usable in later messages

As a member, I can refer to an image already created in this chat so REIGN can see it and reuse the original bytes.

Acceptance criteria:
- Generated originals stay on the persistent Workmates disk and remain listed after restart.
- Every file has a stable ID, filename, creation context and an authenticated download.
- A later request receives a catalog of actual saved files; recent or explicitly selected images are supplied as visual context.
- “This image” resolves to an explicit selection first, otherwise the latest relevant image; multiple ambiguous images prompt a choice rather than inventing a missing file.
- Files from another group, future messages and invalid IDs cannot enter a request.

## S2 Choose assets from the chat

As a member, I can select one or more saved images from a card or asset picker without downloading and reuploading them.

Acceptance criteria:
- Image cards and full screen previews offer Use in chat and Upload to Drive.
- The composer shows selected images and supports removing a selection.
- Selections are bound to the group and saved with the sent message.
- A chat-level asset picker supports up to ten images, including images from older messages.
- The card clearly says Saved in this chat; changing groups or logging out clears unsent selections.

## S3 Reuse images in Word and PowerPoint

As a member, I can use saved images inside a Word document or as PowerPoint backgrounds.

Acceptance criteria:
- A Word export embeds selected images in order with captions; ten images work. Ordinary images are embedded byte-for-byte. Oversized sets use optimized export copies while originals remain unchanged.
- A PowerPoint export embeds image bytes and supports full-slide backgrounds, readable foreground text and ordinary image slides.
- Existing originals are retained. Exports have stable authenticated downloads and appear in the same generation UI.
- Tests reopen DOCX/PPTX packages and verify image content and slide/page structure, not just filename extensions.

## S4 Make image slideshows

As a member, I can turn up to ten saved images into a playable MP4 slideshow with transitions.

Acceptance criteria:
- The exporter supports fade, slide, wipe and dissolve transitions with bounded timing.
- Output is H.264 MP4 with an even frame size and browser-compatible pixel format.
- Tests decode actual frames and check duration, image ordering and frames inside a transition.
- Missing files, unsupported images and canceled jobs produce clear errors; no false success or fabricated download.

## S5 Generate a batch and compose it

As a member, I can request up to ten images and then use the saved batch in a document, presentation or video.

Acceptance criteria:
- Each generated image is saved individually with its source prompt and stable ID.
- A partially failed batch keeps successfully saved images and reports what failed.
- The composition uses saved originals, including images created earlier in the same request.
- Tests exercise ten generated fixture images followed by a real export without paid image calls.

## S6 Optional Google Drive copies and chat linking

As an administrator, I can link Google Drive folders to a chat; as a member, I can copy an image to one of those folders.

Acceptance criteria:
- Each image offers a destination picker for connected chat folders and optional subfolder.
- Copies preserve the original image format and filename; they are not converted to Google Docs.
- A confirmed copy records the remote ID/link and destination on the image, and does not remove the chat copy.
- Group scoping, CSRF and Drive folder ancestry are enforced for every save.
- Without a Google connection, the UI offers the existing setup/link flow and never claims an upload happened.

## Verification gates

Automated API, permission, model-context, batch and binary export tests are required before deployment. Live account consent and authenticated browser acceptance checks must be recorded separately; API tests do not count as completed UI acceptance. Google account setup is still required for live Drive writes.


## Acceptance run

| Story | Automated result | Browser/live gate |
| --- | --- | --- |
| S1 persistent references | Passed: actual vision payloads, durable selected focus, restart preservation, current/future/group boundaries | Signed-in browser check pending |
| S2 asset selection | Passed: ten-image cap, ordering, removal, selected message references, clear on navigation hooks | Signed-in picker interaction pending |
| S3 Word and PowerPoint | Passed: ten embedded original image hashes, real PPTX background image, source metadata and downloads | Open exports from signed-in UI pending |
| S4 MP4 | Passed: ten-image tool export, H.264 decode, duration and real fade/slide/wipe/dissolve frames; cancellation exits | Browser playback/download pending |
| S5 batch composition | Passed: ten generated fixture images to real Word, PowerPoint and MP4 in one chat job; partial failure keeps images and blocks silent batch retry | Paid production batch not exercised in this run |
| S6 Drive copy | Passed: group scope, original image bytes/MIME, confirmed receipt, CSRF and failure handling with simulated Google transport | Google OAuth client/consent still required |

The secure browser sign-in request was declined during this session. No browser credentials were entered through model-visible tools, no sign-in was bypassed, and API/unit tests are not claimed as completed signed-in UI acceptance. Deployment health and public source delivery are checked separately after publishing.

Example end-to-end scenarios:

1. Given a saved skyline image, select Use in chat, ask for a PowerPoint background, then download a PPTX containing that same image.
2. Given ten saved images, select them in order, choose Word, send the request, then open a DOCX with all ten images and captions.
3. Given those images, choose Video, request fade transitions, then preview and download a playable MP4.
4. Given a connected group Drive folder, choose Upload to Drive on an image, select the destination, and see a confirmed Drive-copy link while the chat original remains available.

## S7 Mobile chat and shared group files
As a group member, I want a full-height mobile conversation and easy access to everyone's saved work.

Acceptance criteria:
- At widths up to 850px, the header becomes one compact toolbar; groups, admin actions and the shared work panel open in a left hamburger drawer.
- The drawer closes with its close control, backdrop, Escape or group selection, and traps keyboard focus while open.
- Only messages scroll. The composer remains at the viewport bottom, follows mobile keyboard viewport changes and respects device safe areas.
- A Latest messages control appears when scrolled away from the bottom and jumps to the newest messages without forcing readers down on each refresh.
- Files & work opens the shared document/file list for any member, and generated attachments appear next to the assistant response as well as the originating request.
- Every invited member can list, preview and download the same saved spreadsheet/image bytes. Canvas edits are visible to other members and use existing version conflict checks.
- XLSX previews show bounded cell values for up to ten sheets, 100 rows and 26 columns without executing formulas, macros or external links. Original downloads remain intact.
- Unauthenticated and nonmember requests remain blocked.

Verification: member-session sharing/download/preview/Canvas checks and mobile navigation/viewport behavior checks pass automatically. Authenticated production mobile browser acceptance remains pending; these checks do not imply simultaneous cell editing of binary XLSX files. Edit downloaded spreadsheets in a spreadsheet application; shared Canvas documents support versioned edits in Workmates.

## S8 Voice notes, notifications and contact invites
- Any group member may record up to three minutes / 6 MB, listen locally, send, retry safely or discard. Recording never auto-sends. Group members can play/save durable notes; other rooms and signed-out requests cannot fetch them.
- Email invitations remain bound to the intended email and single use; phone-share invitations are single-use bearer links with a seven-day expiry. Any group member can invite; private solo rooms cannot.
- Existing recipients get a notification bell and an invitation prompt on login. Accepting an invite requires the matching signed-in recipient. Reading/accepting another user's notification is blocked.
- Email status distinguishes accepted by the relay, failure and missing configuration. No claim of inbox delivery follows from relay acceptance alone.
- Contact picking requires a user gesture and supported browser. Only chosen contact details enter the form; full address books are never uploaded. SMS opens the user's messaging app with the invite; it is not unattended SMS delivery.

## S9 Personal backgrounds and Agent Drive
- Users choose Clean, Cosmic, Aurora or Sunset backgrounds, or upload PNG/JPEG/WebP up to 6 MB / 20 megapixels. Images are resized and re-encoded with metadata removed. Strength is adjustable from 0 to 45%.
- Preferences persist server-side per user; uploaded backgrounds are private to that user and may be deleted.
- Agent Drive combines this group's saved images, generated files and versioned Canvas documents with its connected Google Drive mounts. Filters, previews, downloads and Canvas editing remain group scoped. Administrators can connect more folders; other members can browse connected folders.

## S10 Private room and live voice
- Talk privately creates/reopens an owner-only room. Even other workspace admins cannot list or open it. Group transcripts are not copied into the private room. Its own saved history persists between visits.
- Private UI follows the supplied dark reference: circular floating controls, smoky eye, soft bubbles, fading live captions and a bottom text composer.
- Call REIGN opens immediately with a phone-style ringing state and starts voice after the private room is ready; canceling aborts the pending connection. Emojis can be inserted while typing.
- Starting voice requests microphone permission and establishes an OpenAI WebRTC speech-to-speech session. Voice activity detection supports hands-free turns/interruptions. Mute disables microphone tracks; End, navigation, backgrounding and a fifteen-minute call timer close media resources.
- The server signs the voice handshake; the permanent API key never reaches the browser. Text chat uses the configured GPT-6 Astra model; live voice uses the dedicated configurable REALTIME_MODEL (default gpt-realtime-2.1).
- Live user/assistant transcript turns are saved only in the private room and deduplicated by event ID. Typed messages may be sent during the live session. If voice cannot connect, private text remains available.
- Live audio itself is not recorded. Live voice has no document/research tools; end the call and use the private text composer for those actions.

Validation boundary: automated member/owner isolation, saved audio bytes and Range playback, transcript deduplication, notification acceptance, themes and proxy checks run with fake OpenAI transports. Actual microphone playback, recipient inbox arrival and native contact/SMS handoff require device acceptance. These are not marked passed by automated tests.

## S11 Public signup and room ownership
- Anyone may create a member account with a unique email, name and password of at least fourteen characters; supplied platform roles are ignored. Duplicate emails never overwrite an account. Signup is limited per source IP.
- Signed-in users may create rooms. The creator becomes the owner and a member; ownership survives restarts. Owners may configure their own workmate and manage members. Joining another room does not confer ownership.
- Existing shared rooms receive the existing platform administrator as owner. Solo conversations retain owner-only access. Members may share invitations to rooms they belong to; platform administration remains separate.
- Public signup does not include email verification or password-recovery delivery in this release.

## S12 Call connection feedback and orb
- A visible phone/ringing indicator accompanies the ringtone, then shows microphone, connecting, connected, failed or ended states.
- A forty-five-second startup deadline stops a stalled call and releases microphone/peer resources. Provider rejection codes are surfaced without exposing secrets; server logs record only a status/code or exception class.
- The voice session explicitly requests audio output and requests a short spoken greeting on session creation. The speaker-unlock fallback remains available for browser playback restrictions.
- The previous eye/pupil is replaced with a round, luminous smoky orb with separate ringing/listening/speaking treatments and reduced-motion support.
- Automated tests validate the greeting request, connected/ended/failed states, mute and media cleanup. Real microphone/provider audio playback remains pending explicit browser sign-in approval after the prior sign-in decline; no automated transport test is represented as hearing REIGN speak.

## S13 Shared REIGN walkthrough — preview implementation
- Room members join one active, six-person call. The host opens saved Canvas work, generated presentations, images or bounded imported PDF/Office text previews; every participant follows the same page and highlighted field.
- Membership scopes calls, signaling and shared assets. Only the host controls REIGN and stage. Stale stage revisions return 409. Nonexistent fields are rejected.
- REIGN uses actual saved-work tools, can pause/resume at the current page, and can persist agreed decisions and tasks. Typed questions persist once and are forwarded to REIGN when connected.
- Requesting a new member displays a recipient-confirmation prompt; no invitation sends automatically. Private-to-group context promotion remains pending.
- Participant microphones use WebRTC; the host mixes participant audio for REIGN and forwards REIGN audio to the group. CALL_ICE_SERVERS_JSON may configure a TURN relay. Without TURN, restrictive-network calls remain unverified.
- Saving a useful voice clip requires all active participants to consent. Joining, leaving or revoking consent stops recording. Unsaved clips require a leave/discard confirmation.
- Automated permission, synchronized stage, optimistic concurrency, tool idempotency, consent and safe-render tests pass. True multi-device media and audible provider playback have NOT passed acceptance. Production sign-in retry remains blocked by the earlier declined approval; no alternate login route was used.

## S14 Dashboard before chat
- After normal login, open Home rather than automatically entering the first room. Existing Canvas deep links and invitation acceptance still open their destination.
- Match the green-and-white reference with saved light/dark appearance, a project idea composer, optional browser voice dictation, REIGN toggle, recent-room carousel and conversation list.
- List real latest message text, activity time and membership counts; sort recent activity without inventing unread counts or teammates. Filter groups or private REIGN rooms. Private does not imply person-to-person direct messaging.
- Creating a project saves the room and its brief, opens the chat, optionally enables REIGN, then opens the existing invitation confirmation form. Automatic contact recommendations and dashboard attachment upload remain pending.
- Home is available in the navigation drawer. Rightward swipes starting within 32px of the mobile left edge open it; leftward swipes close it. Vertical scrolling, short gestures and form/media interactions are protected.
- Unit tests were written red before implementation, then passed for summaries, sorting/filtering, project title limits, project create/open/settings/invite flow and swipe intent. Signed-in mobile visual acceptance remains pending.

## S15 Dashboard shortcuts and meeting screen presentation
- Home includes Alambda.com, AgentSpace Mail (https://alambda.systems/agentspace/) and https://api.alambda.com/feed/ as external quick-access links with safe new-tab handling.
- Active group participants can choose a screen, window or tab through their browser's display picker. No camera or system audio is captured. Unsupported browsers show a clear fallback; mobile members can still view the presentation.
- One presenter holds the shared screen stage. Other members see that presenter's video, with a connecting state while media negotiates. The source participant and stream must match the server's room-scoped presentation state.
- Stop sharing or the browser's stop control releases video tracks/senders and returns to synchronized saved documents. Leaving releases capture; tab switching keeps the group meeting connected.
- Meeting controls include People +, Share screen / Stop sharing, full-screen stage, mute and Leave. The participant strip identifies the group; REIGN stays alongside the stage.
- REIGN does not receive live screen video in this release. Her synchronized narration uses saved documents and images only. Actual two-device display capture and audio remain device acceptance items.
- TDD: presenter endpoint initially 404 and screen-owner function missing; then permission, exclusive-presenter, source validation, picker/cleanup and destination tests passed.

## S16 Bring saved files into live voice
- Files buttons in private and group calls open a translucent floating canvas, with source-room picker, saved documents/slides/images, page controls and downloads. Tap the preview or expand to fill the screen; mute/end controls stay available and preview controls do not close the audio connection.
- On desktop, a voice-opened canvas sits beside the private voice interface. On mobile it floats above the call and can expand. Imported PDF/Office files retain the current text-preview limitation.
- Private voice exposes find_call_files and open_call_file. REIGN searches real accessible filenames/document titles, asks for clarification on ambiguous matches, and opens a returned ID. Opening returns bounded actual page text; saved images are resized and sent to the active voice session. No live screen video is sent.
- Search excludes other users' private rooms and rooms the caller cannot access. File reads recheck room/asset scope. A private caller may explicitly open shared work they can already access; this does not invite others or copy group content into other users' private rooms.
- In group calls, the host/REIGN stage opens the floating canvas on participants' screens; page navigation stays synchronized. Other members may inspect locally and ask REIGN to open a saved item for everyone. Closing a preview leaves the call connected.
- Discuss with REIGN submits the selected actual page to private live voice, or asks the group voice host to read/open the saved item. Typed and spoken questions may follow.
- TDD: file context route/search initially failed; bounded context, accessible search, room isolation, actual voice tool lookup/open and duplicate-event tests passed. Real spoken tool invocation and two-device audio remain pending signed-in acceptance.

## S17 One appearance across all pages
- The saved light/dark preference applies to dashboard, login, group chat, navigation, Agent Drive, dialogs, Canvas, previews, group calls, private voice and the floating call-file canvas.
- Theme controls are available at login, in workspace navigation and in both call headers. Dashboard light/dark controls change the same preference. No reload or call restart is needed.
- Native input color scheme follows the preference. The light private-call view uses the Workmates green-and-white palette; the dark view keeps the smoky orb and green canvas accents.
- TDD coverage initially failed for missing workspace dark theme; global surface/control coverage and existing dashboard/project flow pass. Signed-in device visual acceptance remains pending.

## S18 Group and call join alerts
- Joining a shared group through account creation, a shared invite link or notification acceptance notifies existing room members. Joining/starting the live call sends a separate Join call alert. The actor receives no self-alert; private rooms emit none.
- Alerts are durable in the notification bell, recipient scoped, and reconnect alerts are suppressed for sixty seconds. Rejoining the same active participant does not create another alert.
- While Workmates stays open, polling displays a fresh join popup with an Open group / Join call action. Displayed alerts are deduplicated per signed-in account/device; stale alerts remain in the bell without ringing repeatedly.
- Join alerts settings in Home/navigation opt into a short sound and phone/browser notifications. Browser permission is requested only on Save when enabled. Audio requires a gesture after reload. A same-origin service worker displays supported phone notifications and routes clicks to the group; it does not cache app/API data.
- Closed-app/background push delivery, SMS and actual phone calls are not enabled. Browser throttling, notification permissions and phone settings can limit alerts. These limits are stated in settings.
- Regression fix: frontend proxy now allowlists and forwards q for call-files and kind/asset_id for call-item. Unknown or duplicate query keys remain rejected; the earlier frontend block on voice file lookup is fixed.
- TDD: new member/call alerts absent, alert UI missing, worker returned 404 and allowed file-query requests returned 400 before implementation. Recipient/dedup, fresh-popup, worker and query forwarding tests passed. Actual phone notification/sound delivery remains unverified on-device.

## S19 Mobile composer call action
- The approved Call with REIGN action is pinned above the message input, displays actual group member names, and starts the shared call plus host REIGN voice connection. Other members receive join alerts and explicitly join/allow their microphone.
- Secondary Images, Voice note, Dictate and Send controls remain thumb-sized at phone widths. Private conversations do not expose a group-call action. Dark human-message contrast is corrected.
- Composer presence/name summary and host/participant call-entry regression tests passed. Real two-device audio remains separate acceptance.

## S20 Customer entry, signup sheet and transactional mail
- Anonymous home visitors see a responsive early-access landing page. /waiting-list always opens it; /app opens the member application and /signup opens account creation. Signed-in home visitors retain their dashboard. Existing invite, file, room, Drive and recovery fragments route into the member app.
- Waiting-list records capture name/email/team/interest plus explicit contact consent, persist once per email, and are visible/exportable as a formula-safe CSV only to administrators. Signup confirmation and administrator lead emails are queued; no lost lead if email fails.
- New self-service accounts receive an email verification link. Password reset requests use uniform responses, rate limits, hashed 30-minute single-use tokens and no automatic login. A successful reset revokes existing sessions and queues a security notice.
- Optional notification/reminder email requires verified ownership and explicit opt-in; disabling it cancels queued optional notification mail. Password recovery and security mail remain transactional.
- Mail payloads are encrypted in a persistent outbox, retry with backoff, expire sensitive links, and are cleared after submission/final failure. The encryption key is a private runtime file beside the persistent database, never source-controlled. Administrator delivery status returns metadata only, never tokens or mail bodies.
- Personal reminders save a due time and create a durable notification when due. Verified, opted-in users also receive email. Browser/phone popup settings remain separate.
- cPanel relay restored after the configured file was found missing. A signed real test email to the administrator received HTTP 202 accepted from the mail server. Inbox delivery is checked separately; accepted is not represented as inbox receipt.
- Tests cover landing/app separation, waitlist deduplication/admin scope, uniform recovery responses, token replay/expiry, session revocation, encrypted outbox clearing, verification/opt-in, and reminder date validation. An initial growth fixture needed correction before its persistence tests ran; the waitlist insert then failed and was fixed. No strict red-before-code claim is made for that fixture repair.
