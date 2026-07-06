# Creative Director — Reel Reads: the story so far

_Written 2026-07-04. The human-readable version. The machine-readable companion is
[LLM_HANDOFF.md](LLM_HANDOFF.md)._

## What this is

**Creative Director — Reel Reads** is the honest AI craft critic for short-form
video (Instagram Reels / YouTube Shorts). A creator uploads a reel (even an
unposted draft); a vision model watches the actual frames and returns a "craft
read": what the reel is, what's working, blind spots with timestamps, and ONE
prioritized fix. If the model can't ground a critique in what's actually on
screen, it says nothing rather than inventing feedback. No virality scores, no
"post at 9am" — the refusal to predict performance IS the brand.

- **Live on the App Store** (iPhone): id6784386221, "Creative Director — Reel Reads"
- **Live on the web**: creative-director-psi.vercel.app
- Solo founder (Vardaan), built with Claude as the engineering pair.

## The journey in eight chapters

### 1. The virality era, and why it died
The project began as a virality-prediction tool: scrape winners, extract
features, predict what performs. Reality check after real analysis: YouTube→
Instagram craft-feature transfer was Spearman +0.23 at n=1,649 — statistically
real but useless for prediction (an early +0.49 was small-sample noise).
Nothing observable reliably predicts views. Instead of shipping a dishonest
score, the finding became the positioning: **2026-06-17, full pivot** to a
video-understanding craft critic that refuses to promise performance.

### 2. The corpus and the pipeline
~6,800 Instagram reels scraped (one-time, via Apify) across four niches —
fitness (~4,769 grounded), food (~725), travel (~648), fashion (~655) — then
featurized on a rented RunPod A100 running Qwen2.5-VL via vLLM (whole-corpus
craft reads for roughly $5 per 15k reels). The corpus powers benchmarks,
niche statistics, and examples — it is deliberately NOT in the iOS app (IP
cleanliness) and is treated as a bootstrap asset, not the moat.

### 3. Making the reads honest (the hard part)
A vision-language model will happily fabricate critique. The engineering that
prevents it:
- **Two-pass grounding gate**: a separate pass tries to refute each note against
  transcript/caption/thumbnail evidence; unsupported reads are SUPPRESSED (the
  user sees "what looked good" instead of invented flaws). One pass can't
  self-calibrate; two can.
- **Intent guard**: the fix must never fight the reel's deliberate structure
  (e.g. "name the hotel at 0:00" on a reveal-format travel reel). Deployed with
  self-consistency voting; ~2,011 reels re-levered, 243 suppressed.
- **The lever**: one prioritized, timestamped fix promoted from the read's own
  top blind spot (grounded by construction — a lever invented from a text
  summary confabulated ~15% of the time, so we don't do that).
- QA across niches: ~90–94% "useful", 99–100% "respects intent", ~89%
  frame-level grounded. Validation lives in scripts, not vibes — prompts are
  never re-tuned without re-running the QA harness.

### 4. The product around the read
- **Library** (every read), **Growth** (Creator DNA: a deterministic fingerprint
  of style + recurring craft gaps, plus an "am I improving?" trend — counted
  from stored reads, no LLM, no hallucination surface).
- **Feedback flywheel**: one-tap Helpful / Not useful / Not in my reel on every
  note — labeled training data from day one.
- **Revision loop** ("did my fix land?"): re-upload after editing; a TWO-VERSION
  verifier watches old and new frames and answers Fixed / Still there / Can't
  verify. Built after discovering a single-version verifier FABRICATED
  "resolved" on unedited reels — the two-version design was validated 4/4
  against that failure.
- **Ideas from your DNA** (built, currently dark behind a flag): grounded
  ideation from the creator's own reads — citation-validated against their real
  uploads, server-stamped statistics, honest empty state. Regenerates rotate
  mandatory creative angles so "show me another" explores structurally.
- **Niche honesty**: the selected niche is a hint, not a fact (the model
  describes what it sees; a food reel filed as fitness reads as a food reel);
  a conservative mismatch detector offers a one-tap switch; a "Something else"
  niche exists for content outside the four corpora and degrades the
  comparisons honestly instead of faking them.

### 5. Becoming an app
Capacitor 8 wraps the same React codebase (bundled assets, not a remote
webview). Native-specific work: bearer-token auth (webviews can't share
cookies), Sign in with Apple (RS256 verify against Apple JWKS), native-first
IA (opens to sign-in; New/Library/Growth tabs), iPhone-only, no third-party
content in the binary. iOS builds run on Codemagic's cloud Macs (founder is on
Windows) — surviving a genuine signing gauntlet (stale certs, invalidated
profiles, build-number collisions), now stabilized with a persistent signing
certificate so builds stop revoking each other.

### 6. Shipping
- **1.0 approved on the first submission** — no rejection — and went live
  2026-07-01. (The review-note prep — passwordless demo login instructions,
  accurate Content Rights answers — did the work.)
- **1.0.1** (approved ~2026-07-03): coach-first read order, copy-as-checklist,
  resilient upload waits, early-state warmth, niche-mismatch chip, header
  cut-off fix, text-zoom pin, HEVC/.mov support.
- **1.0.2** (ready to build): camera fix (missing microphone permission — iOS
  killed the capture UI), portrait-rotation baking in the transcode, leaner
  upload screen, "Something else" niche, and six stability fixes from a
  26-agent adversarial bug sweep.

### 7. Testing round 1 (friends) — what it taught
Real users immediately surfaced: header controls cut off on some iPhones (a
no-shrink flex group + iOS text zoom scaling the webview), .mov/camera uploads
failing (iPhone records HEVC; the lean server's OpenCV can't decode it →
transcode fallback via PyAV; camera additionally needed the mic permission),
walls of text and em-dash-heavy copy on the entry screen (an AI-writing tell —
now scrubbed), and screen-recorded reels skewing reads (fixed socially: a
private key-gated reel-grabber tool testers use to fetch clean mp4s, kept
entirely outside the app).

### 8. The business thinking
Three researched documents govern strategy:
- **STRATEGY.md**: fitness-creator wedge, retention-first sequencing, freemium
  at $9.99 triggered on retention signals, bootstrap-by-default. Do-not-do list
  includes: no virality features, no trend feeds, no paid ads pre-retention,
  no scraping in the product.
- **EXIT_ANALYSIS.md**: realistic 12-month buyout is $50–500K and MRR-driven;
  micro-SaaS trades at 3–5× SDE; the only asset that survives diligence as a
  moat is the labeled outcome dataset at 10K+ verdicts. Plausible strategic
  buyers: Canva, Descript, Adobe. The moat today is honesty positioning +
  per-creator data compounding, not technology.
- **LAUNCH_KIT.md**: ready-to-fire founder-led launch assets (X thread, TikTok
  script in our own beat-sheet format, Reddit post, creator DM template) and a
  week plan. Realistic goal: 100–200 signups; D7 <15% = stop outbound and fix
  the first session.

## Economics (current)
- Per read: ~3–8¢ COGS (DeepInfra Qwen-VL vision calls dominate; Whisper
  transcription and text calls are pennies).
- Fixed: ~$10/mo Railway (always-on API + volume), $99/yr Apple, Vercel free
  tier, R2 storage cents. Reel-grabber: ~fractions of a cent per fetch.
- No revenue yet by design — monetization triggers on retention proof.

## Where things stand today (2026-07-04)
**Live:** App Store 1.0.1 + web; all backend fixes through the bug sweep are
deployed (HEVC + rotation, audio-only guard, revision honesty, grabber
hardening, niche honesty, "other" niche).
**Ready:** 1.0.2 build (camera fix + frontend batch) — one Codemagic click +
one ASC submission away.
**Next (launch-gating):** usage telemetry + KPI sheet (can't be backfilled),
Resend transactional emails (needs the founder's API key), then firing the
launch kit. After that: the v1.2 "post-ready" bundle (captions, audio brief,
Ideas flip), Meta OAuth for import-your-reels, and the Wabi-style first-run
glow-up.

## The one-paragraph pitch (for anyone new)
Every AI creator tool sells virality predictions that don't work. Creative
Director watches the actual frames of your reel and tells you the truth about
the craft — one grounded, timestamped fix at a time — then verifies whether
your edit landed, and builds a private Creator DNA of your style and growth.
It refuses to promise views, and that refusal, backed by an accumulating
dataset of verified diagnosis→action→outcome loops nobody else collects, is
the product.
