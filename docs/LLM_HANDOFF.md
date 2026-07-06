# LLM HANDOFF — Creative Director / Reel Reads

_Machine-oriented state document. Written 2026-07-04. Human narrative:
[PROJECT_HISTORY.md](PROJECT_HISTORY.md). Read this whole file before making
changes; the GOTCHAS section encodes expensive lessons._

## 0. Identity & constraints (non-negotiable)

- Product: "Creative Director — Reel Reads". Honest AI craft critic for
  short-form video. BRAND RULE #1: never predict/promise performance. Banned in
  ALL user-visible output and generated content: views, reach (as a metric),
  virality, trending, algorithm, engagement, "this will work". Validators
  enforce this in ideas.py; prompts enforce it in craft reads. Do not weaken.
- Suppression over fabrication, everywhere: if a model output can't be grounded
  (citations, frames, evidence), show an honest empty state. Never filler.
- All statistics shown to users are SERVER-COMPUTED (fingerprint.py,
  progress.py, ideas digest). The LLM is forbidden from writing numbers.
- App Store declarations (must stay true): no third-party content in the iOS
  app; no scraping in the product; accurate privacy label. Scraping tools exist
  ONLY as unlinked backend/tester utilities.
- Explicit-link rule: never infer user intent from heuristics where an explicit
  link exists (revision loop uses ?prior=/prior_video_id; ideas use ?idea=/
  idea_id). A heuristic verifier once fabricated "resolved" verdicts.
- Owner (Vardaan, naadvar@gmail.com) is solo, on WINDOWS. iOS builds only via
  Codemagic cloud Macs. Owner clicks: Codemagic builds, ASC submissions,
  Railway/Vercel env vars, Apple portal. You (the LLM) do everything else.
- Secrets: never echo tokens/keys in prose. Write to files. Known-exposed (both
  flagged for rotation, not yet done): a DeepInfra key (in old chat logs) and
  the current Apify token (pasted in chat once).

## 1. Deployment topology

| Piece | Where | Deploy trigger |
|---|---|---|
| FastAPI backend (api/, creative_director/) | Railway "creative-director-api-production.up.railway.app", Hobby $10/mo, /app/data volume | push to main → auto-deploy (~1–3 min) |
| React frontend (frontend/) | Vercel "creative-director-psi.vercel.app" (+ /api proxy → Railway) | push to main → auto-deploy |
| iOS app | Capacitor 8 wrap, BUNDLED web assets (dist), NOT remote webview | Codemagic build (owner clicks) → TestFlight → ASC submit |
| Corpus DB | R2 bucket → downloaded to /app/data at boot | scripts upload to R2, then Railway redeploy |
| User data | userdata.db on the Railway volume (SEPARATE from corpus DB) | survives all redeploys; never overwrite |

- Web deploys are INSTANT on push. iOS UI changes reach phones ONLY via a new
  Codemagic build + App Store review (updates take hours–a day).
- R2 env keys on Railway must be UPPERCASE (R2_...); lowercase silently fails.
- Local dev: Windows, repo at C:\Users\naadv\creative-director, venv at
  .venv (run `./.venv/Scripts/python.exe`), local corpus DB at
  data/creative_director.db, local userdata at data/userdata.db. Bash tool on
  Windows: heredocs/inline-python with quotes often exit 127 — write scripts to
  scripts/tmp/*.py and run them; use `git commit -F msgfile`. Python stdout
  needs sys.stdout.reconfigure(encoding="utf-8").

## 2. Repo map (roles, not exhaustive)

- api/main.py — app factory; routers: health, auth, instagram, me, corpus,
  videos, tools (self-gating), + ingest/analyze_handle/upload behind env flags.
- api/routers/upload.py — THE upload job. ALLOWED_NICHES (incl. "other"),
  _probe_duration (PyAV→cv2), _source_rotation (cv2 CAP_PROP_ORIENTATION_META),
  _transcode_h264 (PyAV; bakes rotation; audio stream-copy; try/finally tmp
  cleanup), _ensure_decodable (cv2-check → transcode), _run_job pipeline:
  transcode → thumbnail → transcript (DeepInfra Whisper on the file, no
  ffmpeg) → perception → craft read (retry ×2 on suppression) → gate →
  synthesize lever → niche-mismatch stamp → revision verdict (two-version)
  → durable Upload row write → optional email. In-memory _JOBS dict (lost on
  restart; client polls tolerate 5 misses).
- api/routers/me.py — fingerprint, progress, uploads list, DELETE upload,
  PATCH /me/uploads/{id}/niche (mismatch switch), GET /me/idea, idea feedback.
- api/routers/videos.py — craft-read payload (read + meta incl. is_upload,
  niche; suppressed → strengths from done_well), file/thumbnail serving.
- api/routers/tools.py — PRIVATE tester reel-grabber (/tools/reel-grab).
  Gated: 404 unless API_TOOLS_KEY set; Apify instagram-scraper (directUrls,
  metadata only) → server streams mp4 (SSRF-guarded to IG/FB CDNs, 300MB cap).
  NEVER link from the app.
- api/auth.py — bearer token (native) FIRST then session cookie (web);
  make_token (itsdangerous); verify_apple_identity_token (PyJWKS, aud
  com.creativedirector.app); email gate = passwordless.
- creative_director/advice/craft_xray.py — the read engine. Prompts treat the
  filed niche as UNVERIFIED hint. _incomplete() triggers the single retry
  (missing fields OR CJK code-switch leak, overlay text exempt).
  sample_frames_hires (12 frames @720p), extract_craft_read,
  ground_and_gate (two-pass), synthesize_opportunity, verify_fix_addressed
  (TWO-VERSION: 8 old + 8 new frames; old file missing → None → cant_verify),
  compare_revision (fixed | still_there | cant_verify).
- creative_director/advice/niche_guess.py — conservative keyword mismatch
  detector; "other" mode suggests a niche only at score ≥4.
- creative_director/profile/fingerprint.py + progress.py — deterministic DNA
  aggregations over stored Upload.craft_read rows (no LLM). "other"/unknown
  niche → "You're a creator..." (never "a other creator").
- creative_director/profile/ideas.py — Ideas from your DNA (feature-flagged
  dark). Citation validation vs real upload ids, banned-phrase +
  population-stat regexes (spatial % allowed), difflib remix rejection (vs own
  reels AND prior ideas), angle+anchor rotation on regenerates, cache_key =
  hash of grounded read ids, 5/day cap, honest empty state.
- creative_director/storage/models.py — corpus models (Channel/Video/
  VideoFeatures/VelocitySnapshot) + USER models (User, ConnectedAccount,
  NoteFeedback, Upload [craft_read JSON, prior_video_id, revision_verdict,
  idea_id], CreatorIdea).
- creative_director/storage/db.py — dual engines: corpus (read-only-ish,
  overwritten by deploys) vs userdata_engine (persistent). USER_MODELS bind to
  userdata. _USERDATA_RUNTIME_COLUMNS = idempotent boot migrations (add new
  Upload columns HERE).
- frontend/src/ — React 19 + Vite + TS + Tailwind v4. App.tsx (nav gates:
  native hides Examples, BottomNav; isNativeApp() branches), pages/ (UploadPage
  = New; VideoPage = read + mismatch chip + RevisionVerdict; MyUploadsPage =
  Library; MyDnaPage = Growth, SHOW_IDEAS=false flag lives here; BrowsePage =
  web-only Examples), components/ (CraftRead [coach-first order, checklist
  copy, isUpload prop], IdeaCard [dark], EmailGate [+Apple button on native]),
  api/client.ts (BASE per mode; bearer only on native; mediaUrl() rewrites
  /api→BASE for native).
- codemagic.yaml — CI: build web (mode app → VITE_API_BASE=Railway), cap add
  ios fresh each run, icon gen, Info.plist injection (photo+camera+MIC
  permissions, ITSAppUsesNonExemptEncryption=false, CFBundleVersion=
  $BUILD_NUMBER, CFBundleShortVersionString=1.0.2), Apple sign-in entitlement
  via ruby script (TARGETED_DEVICE_FAMILY=1 iPhone-only), signing via
  PERSISTENT cert key (secure env var CERTIFICATE_PRIVATE_KEY, group
  "signing"; pem also at C:\Users\naadv\ios_dist_certificate_key.pem — never
  commit), publish to TestFlight.
- docs/ — STRATEGY.md, EXIT_ANALYSIS.md, CREATOR_XP_AUDIT.md, LAUNCH_KIT.md,
  IDEAS_FEATURE.md, REVISION_LOOP_DESIGN.md, IOS_SUBMISSION.md, IOS_APP.md,
  PROJECT_HISTORY.md, this file.
- scripts/tmp/ — working scripts incl. TEST HARNESSES (see §5). NOTE: files
  here DO get committed sometimes — never put secrets in scripts/tmp.

## 3. Current state (2026-07-04)

- App Store: 1.0 shipped 07-01 (first-try approval); 1.0.1 LIVE (~07-03).
- 1.0.2 READY, NOT YET BUILT/SUBMITTED. Carries: camera fix
  (NSMicrophoneUsageDescription — the actual root cause of "camera doesn't
  work"), portrait-rotation baking, cancel-reset, is_upload prop fix, resume
  bundle-check, leaner New screen (de-em-dashed copy), "Something else" niche,
  persistent-cert signing. Owner kicks Codemagic → smoke → ASC "+ Version"
  1.0.2 → What's New (rewritten version in chat/LAUNCH context: lead with
  upload-screen + Something else; camera as "more reliable") → submit.
- Portrait/camera: VERIFIED on-device 2026-07-04 — owner recorded in-app on the
  1.0.1 App Store build: upright, with sound, read completed. NOTE the real
  root cause of "camera doesn't work" was the HEVC upload rejection (backend,
  fixed for all clients); the missing mic permission (ships in 1.0.2) turned
  out to be defensive, not the felt bug. Residual low-risk unknown: an in-app
  recording may be H.264 (no transcode), so the rotation-BAKE path for
  native-camera HEVC .movs is confirmed by unit tests + this outcome but not
  isolated on-device; if a portrait .mov ever reads sideways, flip the 90↔270
  mapping in _transcode_h264 (one line).
- Ideas feature: BUILT + backend live, UI dark (MyDnaPage SHOW_IDEAS=false).
  Owner wants staged rollout; flip = one word + push (web), next build (iOS).
- Reel grabber: LIVE + verified e2e. Link = /tools/reel-grab?key=<API_TOOLS_KEY>
  (key in .env + Railway; shareable link in scripts/tmp/tester_link.txt).
- Tester round 1 bugs: ALL FIXED (header/text-zoom verified across widths;
  HEVC verified with real H.265 file; camera fix ships in 1.0.2).
- 26-agent sweep (wf_32d7f094): 13 confirmed bugs → all fixed; 9 candidates
  rejected by adversarial verification.
- Marketing: docs/LAUNCH_KIT.md ready; NOT fired. Strategy says telemetry
  before the spike.

## 4. Pending queue (priority order)

1. Owner: kick 1.0.2 build → TestFlight smoke (camera records; PORTRAIT REEL
   UPRIGHT; Something else chip) → submit 1.0.2.
2. Build: usage telemetry + KPI report (WAU, D7, helpful%, suppression rate,
   revision verdicts). CANNOT be backfilled — highest priority build item.
   NoteFeedback + Upload rows exist; add event logging + a report script
   (feedback_report.py exists as a pattern).
3. Build: Resend emails (welcome, read-ready, day-7). BLOCKED on owner creating
   resend.com account + setting API key on Railway. Email-send stub exists in
   upload pipeline ("optional email" step).
4. Surface ShareCard post-read (component exists, undiscoverable).
5. Fire LAUNCH_KIT (owner posts; you support with assets/replies).
6. On first portrait upload: verify rotation sign (see §3).
7. v1.2 "post-ready" bundle (specs agreed, in chat + partially in docs):
   caption suggestions (grounded in transcript/on-screen text, validator like
   ideas), audio brief (voice-hook timing from Whisper segments + corpus audio
   aggregates: hook_audio_is_voice etc.; treatment advice, never track names),
   THEN optional suggest-only audio matching via weekly Apify metadata batch
   (deep links into IG; never files; web-only surface), Ideas flag flip.
8. Meta OAuth (Instagram API with Instagram Login): dev-mode works for
   manually-added testers WITHOUT review; scope instagram_business_basic;
   professional accounts only; full App Review (2–4 wks) only for public.
   instagram.py router exists but targets the OLD API — needs scope/endpoint
   update. Encrypt ConnectedAccount.access_token BEFORE this ships.
9. Housekeeping: rotate DeepInfra + Apify keys; replace naadvar@gmail.com as
   public support address; LLC + Apple app-transfer when revenue starts;
   reduce web Examples third-party surface post-launch.

## 5. Test harnesses (run these before touching related code)

All under scripts/tmp/, run with `./.venv/Scripts/python.exe` from repo root
(PYTHONPATH=. sometimes needed for api imports):
- retest_gate.py — grounding-gate regression (don't re-tune gate prompts
  without it; "don't re-oscillate" is a standing rule).
- test_ideas.py (28 checks) + test_ideas_live.py / test_ideas_showcase.py
  (real-LLM QA) — ideas validator/gating/cache/diversity.
- test_niche_guess.py (12) — mismatch detector + switch endpoint.
- test_transcode_fixes.py — rotation math, audio-only guard, tmp cleanup.
- test_hevc_transcode.py — real H.265 → H.264 e2e (downloads sample).
- test_mislabeled_read.py / test_ood_read.py — niche-as-hint + OOD honesty
  (real VLM calls, ~cents).
- verify_live_grabber.py / probe_idea_deploy.py — live prod probes.
- deep_sweep_qa (scripts/) — corpus-wide absurdity flags; must stay {}.

## 6. GOTCHAS (each one cost real time — do not relearn)

- iPhone records HEVC .mov by default; lean-host OpenCV can't decode it. The
  transcode fallback exists for exactly this; don't remove PyAV (av>=12) from
  requirements-serve.txt. PyAV 17 does NOT expose rotation on streams — cv2's
  CAP_PROP_ORIENTATION_META (container header, decoder-independent) is the
  rotation source.
- Video CAPTURE on iOS needs NSMicrophoneUsageDescription, not just camera —
  without it the capture UI dies silently ("camera doesn't work").
- iOS system text zoom scales Capacitor webviews → layout overflow. Pinned via
  @capacitor/text-zoom TextZoom.set({value:1}) in main.tsx (native only).
  Header right-group must be min-w-0 (shrink-0 there = cut-off Sign in/out).
- ios/ is NOT committed; `cap add ios` regenerates it every CI run — all
  Info.plist/entitlement changes must live in codemagic.yaml/ci scripts, never
  edited "in Xcode".
- TestFlight rejects reused CFBundleVersion; App Store rejects reused
  CFBundleShortVersionString (bump per store release; currently 1.0.2).
- Deleting ASC distribution certs sends the owner scary "revoked" emails —
  signing now reuses one cert via CERTIFICATE_PRIVATE_KEY; don't reintroduce
  the delete-recreate loop.
- Native webview can't use the Vercel /api proxy: absolute media/API URLs via
  client.ts mediaUrl()/BASE. Cookies don't cross capacitor://localhost —
  bearer tokens on native only.
- Corpus DB is OVERWRITTEN on redeploy; anything user-generated must be in
  USER_MODELS (userdata engine) + _USERDATA_RUNTIME_COLUMNS migration, or it
  will be silently wiped.
- The craft-read model (Qwen via DeepInfra) occasionally code-switches CJK
  into English reads (seen: 洞穴) — _incomplete() retries on CJK in the body
  (creator overlay-text field exempt; may legitimately be non-English).
- Ideas validator: ban POPULATION stats only ("37% of reels") — spatial
  percentages ("text at 80% width") are legitimate craft directions; the
  strict ban suppressed 3/3 live generations. Same for "reach": only
  performance collocations ("your reach"), fitness reels say "reach overhead".
- Suppression is non-deterministic → upload pipeline retries the read once
  (MAX_READ_ATTEMPTS=2) before showing the suppressed fallback.
- Prompt changes to reads/gate/verifier: validate via the scripts in §5 with
  real API calls (cheap), never eyeball-only, never iterate blind ("the
  grounding-gate lesson").
- Apify: reel-scraper input uses "username" (array); resultsLimit is GLOBAL
  not per-profile; includeDownloadedVideo is a paid event (~$0.10/reel) — the
  grabber uses apify~instagram-scraper with directUrls + metadata instead.
  Account earlier hit "Too many outstanding invoices" (now on a new account).
- Shell on this Windows box: inline `python -c "..."` with quotes/f-strings
  frequently exits 127 (snapshot+quoting) — write a script file instead. Em
  dashes in `git commit -m` also break — use -F file.
- App Store Connect mobile app shows "Currently Unavailable" during Apple-side
  outages (check Downdetector + apple.com/support/systemstatus developer feed
  before debugging "blocks" — owner is sensitive about account standing;
  reassure with evidence: live-app lookup id6784386221).
- itunes lookup (https://itunes.apple.com/lookup?id=6784386221) = instant
  "is the app live / what version" probe.
- Owner style (from memory): values DIRECT pushback with named failure modes;
  prefers cheap answer-sheets over heavy automation when a human is in the
  loop; "table features" means stop building new surface, not stop fixing.

## 7. External services & credentials (locations, not values)

- .env (repo root, NOT committed): DeepInfra key (craft_read_* + transcript_*),
  R2 creds, APIFY_API_TOKEN, API_TOOLS_KEY, API_SESSION_SECRET, userdata URL.
- Railway env: same set UPPERCASE (R2!), + API_TOOLS_KEY, APIFY_API_TOKEN.
- Codemagic: App Store Connect integration "codemagic", secure var group
  "signing" (CERTIFICATE_PRIVATE_KEY).
- Vision/LLM: DeepInfra OpenAI-compatible endpoint, Qwen-VL for reads/gate/
  verifier/perception; Whisper large-v3-turbo for transcription; Anthropic
  fallback path exists (_call_anthropic) but is not primary.
- Apple: bundle com.creativedirector.app, app id 6784386221, team = owner
  personal. Sign in with Apple capability ON.
- Corpus source of truth: R2 (db snapshot) + local data/creative_director.db.

## 8. How to work with the owner (process notes)

- He clicks: Codemagic builds, ASC pages, Railway/Vercel dashboards, Apple/Meta
  portals, payments. Prepare exact click-paths + paste-ready text for him.
- Ship rhythm that works: fix → test locally with a script → commit (detailed
  message, Co-Authored-By: Claude) → push (auto-deploys backend/web) → tell him
  what needs a build vs what's already live. Batch iOS changes into versioned
  releases.
- Never start marketing pushes, paid services, or feature flags without his
  explicit go. He tables features often — respect it, queue specs instead.
- When he reports a bug from testers, treat the REPORT as ground truth over
  prior assumptions (the camera bug survived one wrong root-cause; the second
  pass found the mic permission).
