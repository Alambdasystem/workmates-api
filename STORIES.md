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
