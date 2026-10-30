# Workmates TDD record — 2026-10-30

Observed red before implementation:
- swipe_test.js: missing swipeNavigationIntent.
- test_call_workspace.py: new call endpoints returned 404.
- meeting_test.js: missing meeting.js.
- audio_test.js: missing call_audio.js.
- dashboard_test.js: dashboard implementation missing.
- dashboard summary test: last_message missing.
- invalid image highlight test: received 200 instead of 400.
- existing API contract parity test: new call routes absent from OpenAPI.

Green after implementation:
- New call integration tests: membership boundaries, shared stage/revision conflict, scoped signaling, unanimous recording consent, real decision/task tool persistence and idempotency, nonexistent image field rejection, real dashboard summaries.
- Frontend Node suites: assets, audio, dashboard, generation, meeting, mobile, social, solo, swipe.
- Dashboard project flow uses a fake transport. Audio/WebRTC tests use fake provider/peer transports. They do not establish microphone capture, human-audible output or multi-device interoperability.

Device acceptance still required:
1. Sign in with approval; call REIGN, hear greeting, speak, interrupt, mute and reconnect.
2. Join from a second account/device; hear both people and REIGN with no feedback.
3. Navigate/highlight a shared deck on one device and observe the same stage on the other; interrupt and resume.
4. Verify consent stop/join/revoke and save/play a real useful clip.
5. Check both dashboard themes at phone width, browser keyboard, Home navigation and edge swipe.
6. Confirm real email inbox delivery and Google OAuth separately; neither is marked verified.

S15: screen sharing and quick links
- Red: new presenter route returned 404; meetingScreenOwner was undefined.
- Green: only one active presenter, participant ownership, release and membership tests; screen source/stream validation; explicit video-only picker, local preview and track cleanup; all three dashboard link destinations.
- Browser display picker, video transport across devices and fullscreen layout still need signed-in device acceptance. No fake peer test is described as a real screen-share session.

S16: voice-opened floating file canvas
- Red: missing call_files.js; file context endpoint lacked pages; voice search endpoint returned 404.
- Green: actual page/length/untrusted-content context checks; room/asset authorization; accessible title search; private voice lookup/open executes the floating viewer and returns actual page text; duplicate tool events are ignored.
- UI handlers do not invoke endLive/closeMeeting when opening or expanding a file. Closing the call cleans up its viewer. Browser display and real spoken requests remain unverified; no automated test proves audible voice.

S17: global appearance
- Red: dark theme coverage missing for workspace.
- Green: explicit login/chat/call/canvas/dialog theme surfaces and controls; saved dashboard preference still drives the project flow tests.

S18: join alerts and file-query regression
- Red: no member_joined/call_joined notifications; missing alerts.js; /sw.js 404; file query requests rejected with 400.
- Green: scoped durable member/call alerts, no self-alert, same-participant duplicate suppression; fresh/deduplicated safe popup and Join call action; service worker root route/no-cache; exact file-query allowlists, forwarding and rejection of unknown parameters.
- Phone/browser permission and physical audio delivery remain manual acceptance; this release does not claim closed-app push, SMS or telephone ringing.
