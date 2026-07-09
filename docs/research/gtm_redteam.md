# Red-team: what actually goes wrong when we start sharing

_Scope: the GTM in docs/STRATEGY.md + docs/LAUNCH_KIT.md, red-teamed against the codebase as it exists (api/routers/upload.py, api/routers/tools.py, creative_director/storage/kpis.py). Every tripwire maps to a field on the live KPI endpoint (`/tools/kpis?key=Ã¢â‚¬Â¦`) or names the one-line instrumentation gap that must close before launch day._

**Scoring:** Likelihood = chance it bites in the first 90 days. Damage = cost if it does, given that the whole moat is an honesty reputation + a labeled dataset that only accumulates if users stay.

## Risk register (summary)

| # | Risk | Likelihood | Damage | Mitigation cost |
|---|---|---|---|---|
| 1 | DM outreach reads as spam / action-blocked | High | Medium | 0h Ã¢â‚¬â€ discipline + a pacing table |
| 2 | Subreddit self-promo removal or ban | High | Medium | ~2h/wk (already budgeted) |
| 3 | "AI slop critic" backlash | Medium | Medium-High | ~2h prep |
| 4 | Review-bomb from suppressed-read disappointment | Medium | High (tiny rating base) | ~4h eng |
| 5 | Reel-grabber tool becomes an IG-TOS optics story | Low | High (brand) | ~1h ops hygiene |
| 6 | A post hits; cost + capacity collapse | Low-Medium | Medium ($) / High (UX) | ~4h eng |
| 7 | DeepInfra outage/reprice mid-launch | Medium | High during launch week | 1-2 days (already planned; pull it forward) |
| 8 | On-camera face Ã¢â€°Â  founder Ã¢â€ â€™ authenticity attack | Medium | High (it's an honesty brand) | 0h Ã¢â‚¬â€ labeling discipline |
| 9 | Fitness creators bounce off text-heavy critique Ã¢â‚¬â€ and get MORE suppression | Medium-High | High (it's the wedge) | ~1 day eng + prompt QA |

---

## 1. Creator DM fatigue / getting marked as spam

**What goes wrong.** The launch plan calls for 10-15 pre-launch DMs plus 5/day during launch week. Cold DMs from an account the target doesn't follow land in the Message Requests folder (open rates are poor), and Instagram's limits are real: mature, warmed accounts sustain roughly ~20 cold DMs/day; newer or lightly-used accounts get flagged at 5-10 cold DMs/day, and copy-paste text or recipient spam-reports trigger 24-48h action blocks ([Inro](https://www.inro.social/blog/how-many-direct-messages-can-you-send-on-instagram), [Flowgent](https://flowgent.ai/blog/instagram-dm-limits-how-many-messages-you-can-send-daily), [InstantDM](https://instantdm.com/blog/instagram-dm-limits-rules-2026-the-ultimate-account-safety-guide)). Two compounding failures: (a) an action block on the founder's personal account takes down the *entire* founder-led channel (posting, commenting, replying) during the only week that matters; (b) enough spam reports and Meta's classifier starts eating the app link itself in DMs.

- **Likelihood:** High Ã¢â‚¬â€ the template in LAUNCH_KIT.md Ã‚Â§4 is good, but the temptation on a slow day 3 is to send 20 identical DMs.
- **Damage:** Medium. Channel loss for 48h+ at launch, plus link poisoning.

**Cheap mitigation Ã¢â‚¬â€ the pacing table (put this in the calendar, not in memory):**

| Day | Cold DMs (max) | Warm actions first |
|---|---|---|
| T-14 Ã¢â€ â€™ T-7 | 0 | Follow the 15 targets; leave 2 genuine comments each over a week |
| T-7 Ã¢â€ â€™ launch | 3/day | Only to accounts you've already commented on |
| Launch week | 5/day, hard cap | Never two with the same middle sentence |
| Any "action blocked" | 0 for 48h | Full stop, including likes/comments |

Rules: first message contains **no link** Ã¢â‚¬â€ the LAUNCH_KIT opener minus the App Store line; link goes in the reply after they respond. Every DM gets a unique first line (already the rule) *and* a unique middle sentence. Never DM from a fresh "brand" account Ã¢â‚¬â€ the aged personal account with real history is the asset.

**Tripwire:** reply rate < 10% over any 20-DM window Ã¢â€ â€™ stop and rewrite the template before sending #21. Instrument channel attribution first (see Engineering asks): share links as `?src=dm` / `?src=reddit` / `?src=x` and log it into `Event.props` at signup Ã¢â‚¬â€ right now `/tools/kpis` cannot tell you which channel produced a WAU, so channel-level tripwires are blind.

---

## 2. Subreddit self-promo bans

**What goes wrong.** Creator subs (r/NewTubers and its peers) restrict link/self-promo posts to designated threads, and mods in 2026 are primed to nuke "solo dev built an AI tool" posts on sight Ã¢â‚¬â€ the sub has been carpet-bombed by them. A removal is a wasted one-shot launch story; a ban is permanent loss of the top community channel and a public modlog entry. Reddit also silently filters young/low-karma accounts posting links, so the post can be invisible while you think it flopped organically.

- **Likelihood:** High if posted cold. Low with the protocol below.
- **Damage:** Medium Ã¢â‚¬â€ channel loss + the launch-week story spent for nothing.

**Cheap mitigation Ã¢â‚¬â€ the two-week runway (fits the existing 2h/wk community budget):**
1. **T-14:** Start participating for real Ã¢â‚¬â€ give 3-4 genuine, non-tool critiques in Feedback Friday-style threads per week. No links, no tool mentions. This is also product research.
2. **T-3: modmail pre-clearance.** Template:
   > "Hi mods Ã¢â‚¬â€ solo dev, been giving feedback in the Friday threads for a couple weeks (u/Ã¢â‚¬Â¦). I built a free tool that critiques a reel's editing and explicitly refuses to predict views. I'd like to post it once asking for people to tell me where it's *wrong*. Happy to keep it link-in-comments, flair it however you want, or keep it to the designated thread Ã¢â‚¬â€ your call."
   Mods almost always answer, and a pre-cleared post can't be removed as ambush promo.
3. **Post format:** text-first (the LAUNCH_KIT Ã‚Â§3 body is right), web link only, reply to every comment for 6 hours, never argue with a skeptic Ã¢â‚¬â€ agree, and ask them to break it.
4. **One sub per week, maximum.** Cross-posting the same body to 3 subs in a day is the pattern automod is built to catch.

**Tripwire:** post removed or < 50% upvote ratio in the first hour Ã¢â€ â€™ delete it yourself, don't relitigate; try the modmail route at the next sub. Watch `?src=reddit` signups in `events_7d`; if a "successful" post (100+ upvotes) produces < 10 signups, the channel is applause-not-users Ã¢â‚¬â€ stop investing there.

---

## 3. "AI slop critic" backlash

**What goes wrong.** The 2026 creator zeitgeist is openly hostile to AI content tools, and this product has a built-in irony attack: *"An AI is going to lecture humans about craft?"* Expect the quote-tweet dunk, the "training on our reels" accusation, and the top Reddit comment being a one-liner about slop. The risk isn't the criticism Ã¢â‚¬â€ it's the founder responding defensively in public, or the dunk becoming the product's first framing before any user has a counter-story.

- **Likelihood:** Medium Ã¢â‚¬â€ near-certain in tone on Reddit/X replies; a *viral* dunk is less likely at zero-follower scale.
- **Damage:** Medium-High. Framing is sticky, and the product's only marketing asset is its stance.

**Cheap mitigation (~2h of prep, zero ongoing):**
- **Positioning judo, pre-written.** The honest answer is genuinely strong Ã¢â‚¬â€ use it verbatim and identically everywhere, once per thread, then stop:
  > "Fair. Here's the difference: it never predicts views (we tested Ã¢â‚¬â€ nothing observable does), it critiques only what's verifiably on screen, and when it can't verify, it says *nothing* Ã¢â‚¬â€ X% of reads come back as 'no notes' rather than invented feedback. You can tap 'not in my reel' on any line and that's logged against us. If it's slop, it's the only slop that shuts up."
  Fill X% from `/tools/kpis Ã¢â€ â€™ uploads.suppression_pct`. Ship the Read Transparency / published-suppression-stats artifact (already Month 2 in STRATEGY.md) Ã¢â‚¬â€ it is the anti-slop receipt; consider pulling a minimal version ("this week: N reads, M suppressed") forward to week 2.
- **Never hand them the ammunition:** the do-not-do list already bans critiquing famous creators' reels publicly and virality language Ã¢â‚¬â€ those are the two behaviors that convert "skeptics" into "a pile-on."
- **One reply per critic, then disengage.** Write this rule down; launch-week adrenaline will argue otherwise.
- **Data-training question:** have a one-line true answer ready (what uploads are/aren't used for) before someone asks it publicly, not after.

**Tripwire:** on the dashboard, `feedback.by_reason["not_in_my_reel"]` share > 10% of weekly taps Ã¢â‚¬â€ that's the *substantiated* version of the slop accusation (the model described things not in the reel) and it must be treated as a product incident, not a PR problem. `uploads.ungated > 0` is the silent-degradation alarm (fact-check gate not running) Ã¢â‚¬â€ it's already wired to render as `!! UNGATED` in the KPI text; if it fires during a promotion push, halt outbound until it's zero.

---

## 4. App Store review-bomb from suppressed-read disappointment

**What goes wrong.** ~10-15% of uploads come back suppressed (corpus treatment ran ~11%; the pipeline auto-retries regeneration before giving up). The suppressed UI shows "what looked good," but a first-time user who waited 1-2 minutes and got no fix can experience honesty as breakage: *"uploaded my video, it told me nothing, 1 star."* With near-zero installs, the store page is defined by its first 10-20 ratings Ã¢â‚¬â€ three 1-stars among the first ten pins the visible average near 3.x, and a sub-4.0 badge suppresses every future install the content work generates. The audit's P0 #1 (polling can silently hang forever, UploadPage.tsx) is the same review with a different cause: "it just spins."

- **Likelihood:** Medium Ã¢â‚¬â€ mechanically guaranteed to happen to *some* users; the question is only whether they route it to the store.
- **Damage:** High. Ratings are the one asset that can't be redeployed.

**Cheap mitigation (~4h):**
1. **Set expectations before the first upload**, not after: one line on the upload screen Ã¢â‚¬â€ "If we can't verify a critique against your actual frames, we'll tell you less rather than make things up." Then suppression reads as the brand keeping a promise.
2. **Route disappointment inward:** on a suppressed read, show a feedback affordance ("Did we miss something? Tell me") that goes to in-app feedback / support email Ã¢â‚¬â€ never any store-review prompt on that path.
3. **Gate the rating prompt (when one ships) on positive signals only:** fire `SKStoreReviewController` only after a `helpful` tap or a revision-loop **Fixed** verdict Ã¢â‚¬â€ the two moments of demonstrated value. Apple caps prompts at 3/user/year anyway; spend them there. Never prompt in session one.
4. **Ship the audit's P0 upload-resilience fix before any promotion** Ã¢â‚¬â€ the infinite-poll hang is the most preventable 1-star in the codebase.
5. **Reply to every review within 24h** from the support address (already an App Store operational requirement per STRATEGY.md). Template: "You're right that the read said little. That's the design Ã¢â‚¬â€ it won't invent notes it can't verify on your frames Ã¢â‚¬â€ but we clearly didn't earn that moment. DM/email me and I'll look at your reel's read personally."

**Tripwire:** `/tools/kpis Ã¢â€ â€™ uploads.suppression_pct` > 20% for a week (investigate before promoting anything); `uploads.ungated > 0` (gate outage Ã¢â‚¬â€ worse reads AND wrong suppression); App Store rating < 4.0 while total ratings < 30 Ã¢â€ â€™ pause all outbound until 5 happy users (helpful-tap or Fixed-verdict users, asked personally, 1:1) have rated. Check ratings daily during launch week; it's a 30-second glance.

---

## 5. IG TOS optics of the tester reel-grabber

**What goes wrong.** `/tools/reel-grab` (api/routers/tools.py) is a private, key-gated page that pulls a reel's mp4 via the Apify instagram-scraper and streams it to a tester's phone Ã¢â‚¬â€ built so testers don't skew reads with screen recordings. It 404s without `API_TOOLS_KEY` and is never linked from the product. The failure mode isn't Meta enforcement against you (you're an Apify customer among thousands); it's **optics**: a tester shares the keyed URL in a group chat, it circulates as "the app's IG downloader," and now the honesty-positioned product appears to ship a scraper Ã¢â‚¬â€ contradicting the stated "no scraping-based features" compliance stance, handing the slop-backlash crowd (#3) a receipt, and creating an awkward answer if Apple or a journalist asks. The keyed URL is fully self-contained: anyone holding it has the tool.

- **Likelihood:** Low Ã¢â‚¬â€ small tester group, gated route.
- **Damage:** High relative to its usefulness Ã¢â‚¬â€ it's a brand contradiction discovered rather than disclosed, and the disclosure story writes its own headline.

**Cheap mitigation (~1h, ongoing hygiene):**
- **Dark by default:** unset `API_TOOLS_KEY` except during scheduled tester sessions Ã¢â‚¬â€ with it unset every `/tools/*` route (including `/users`, which returns PII) 404s. Note `/tools/users` and `/tools/kpis` share the same key as the grabber; when you turn the key on for a tester, you've turned on the PII endpoints for anyone holding that key. **Split the keys** (tester key vs. owner key) Ã¢â‚¬â€ 30 minutes of work.
- **Rotate the key after every tester batch.** Treat a shared key as burned.
- **Scope the ask:** tell testers to use it only on *their own* reels, and say why in the page copy (one sentence). Grabs are already logged (`logger.info` per fetch) Ã¢â‚¬â€ skim the log weekly for URLs that obviously aren't the tester's handle.
- **Never reference it publicly**, including in build-in-public content. If asked directly, the honest answer is fine ("private tester utility so beta reads aren't skewed by screen-recording artifacts; testers fetch their own reels") Ã¢â‚¬â€ prepared honesty is cheap, discovered scraping is not.
- Long-term: retire it once TestFlight testers can be told to upload original files/drafts, which is the product's real story anyway.

**Tripwire:** grab-log entries from IPs/UAs you don't recognize, > ~10 grabs/day, or any grabbed URL not belonging to a known tester Ã¢â€ â€™ rotate the key that day. Add a weekly 2-minute log skim to the KPI-review ritual.

---

## 6. Capacity + cost if a post accidentally hits

**What goes wrong.** COGS is ~$0.03-0.08/read. A modest hit (200 uploads/day) is $10-16/day of LLM spend Ã¢â‚¬â€ $300-480/mo on a free product against $10/mo infra. Survivable. The real failure is a *front-page* hit (1,000-2,000 uploads/day): $50-160/day in spend, and Ã¢â‚¬â€ worse Ã¢â‚¬â€ the single lean Railway instance grinding through 1-2-minute read jobs serially while every new visitor's upload sits behind them. The existing protections: per-IP cap of 10 fresh uploads/day + 100 dedupes/day (upload.py:43-47) and same-file memoization. The gaps: the caps are **per-IP** (a spike is thousands of distinct IPs Ã¢â‚¬â€ the cap does nothing globally), they're **in-memory** (any redeploy resets all windows), and there is **no global ceiling and no spend-linked kill switch**. The visible symptom is CREATOR_XP_AUDIT P0 #1: polls that hang forever, i.e., the spike converts into first-session bounces and #4-style reviews at the exact moment of maximum attention.

- **Likelihood:** Low-Medium (zero-audience launches rarely hit Ã¢â‚¬â€ but Reddit occasionally decides otherwise, and it's the scenario you're actively trying to cause).
- **Damage:** Medium in dollars, High in wasted once-only attention.

**Cheap mitigation (~4h, do it before the first Reddit post):**
1. **Global circuit breaker:** env var `MAX_FRESH_READS_PER_DAY` (start at 300 Ã¢â€°Ë† worst-case ~$25/day) checked in the upload route next to `_rate_limited`. Over the cap, return an honest 429 the frontend renders warmly:
   > "We're at capacity today Ã¢â‚¬â€ every read costs us real compute and we'd rather slow down than cut corners. Leave your email and you're first in line tomorrow."
   That's an email-capture *and* on-brand scarcity, for one if-statement. Raise the cap by env var when a spike proves organic.
2. **Provider-side hard stop:** set DeepInfra's spend alert ($15/day) and a hard monthly cap now, while it's academic. Same for the Anthropic fallback key.
3. **Require sign-in for upload during promotion windows** if it isn't already the only path Ã¢â‚¬â€ per-account limits beat per-IP limits, and a signup is captured even if the read queues.
4. **Ship the honest-wait state** (audit P0 #1): "taking longer than usual" + push/email-me-when-done beats a spinner, and the read-ready email (Week-1 Resend task) converts queue pain into a retention touch.

**Tripwire:** `uploads.last_7d` pace Ã¢â‚¬â€ more than ~50 fresh uploads in a rolling hour means the breaker will trip within the day (decide then: raise cap or let it hold). DeepInfra dashboard > $15/day. Add p50 upload-to-read-complete time as an event so latency shows up in `events_7d` Ã¢â‚¬â€ today the dashboard can't see queue pain at all.

---

## 7. Single-provider dependency (DeepInfra)

**What goes wrong.** On the lean host, **both** the VLM craft read (Qwen2.5-VL via the OpenAI-compatible endpoint) and transcription (DeepInfra-hosted Whisper on the mp4, `transcript_api_base` in config.py) run through one vendor. A DeepInfra outage during launch week = 100% read failure for hours = a cohort of first-session users who experienced a broken app, plus review risk (#4) and hang risk (#6). A repricing/model-sunset email is slower-moving but changes unit economics under the free tier. The Claude fallback for reads is wired (~2-3x cost Ã¢â‚¬â€ $0.10-0.25/read, survivable); **transcription has no wired fallback** Ã¢â‚¬â€ verify this, because a transcript failure can degrade the gate's primary grounding signal even if the VLM is up (and if perception fails in the wrong way, that's the `ungated` alarm).

- **Likelihood:** Medium over 90 days for at least one multi-hour outage; Low-Medium for reprice/sunset.
- **Damage:** High specifically during launch/promotion windows; Medium otherwise.

**Cheap mitigation:**
- **Pull the multi-vendor A/B forward.** STRATEGY.md schedules the ~50-reel DeepInfra-vs-Claude(-vs-one-more) comparison for Month 2 Ã¢â‚¬â€ run it in the pre-launch week instead (1-2 days, already scoped). The deliverable isn't the winner, it's the *verified one-env-var switch*.
- **Wire a transcription fallback** (Claude/OpenRouter Whisper-equivalent or graceful transcript-absent mode that the gate already knows how to weigh) Ã¢â‚¬â€ this is the un-scoped gap.
- **Keep ~$50 of credit live on the fallback vendor** so a 3 a.m. switch is an env change, not a signup flow.
- **Fail honestly in the UI:** a "reads are delayed Ã¢â‚¬â€ we'll email you when yours is ready" banner state costs little and converts an outage from "broken app" to "honest app having a bad day."
- Never promote (Reddit post, PH launch) without checking provider status first; if an outage starts mid-spike, flip the circuit breaker (#6) to stop new intake rather than minting failed first sessions.

**Tripwire:** `uploads.no_read` climbing intra-day, `uploads.ungated > 0` (perception ran without the gate Ã¢â‚¬â€ the July failure mode, encoded as an alarm in kpis.py), or read p50 latency > 4 min. All three warrant halting outbound before debugging.

---

## 8. The founder not being the on-camera face

**What goes wrong.** The LAUNCH_KIT Video-1 shot list is written for a founder-adjacent woman on camera ("she uploads a REAL recent reel of hersÃ¢â‚¬Â¦"). Creator audiences are forensic about authenticity, and this is an *honesty-branded* product: if she is ever presented as, or allowed to be mistaken for, the founder, the eventual "wait, who actually built this?" thread costs more than any video gained. There's a second-order version: a polished "reaction" video from someone with no visible connection to the product pattern-matches to paid UGC, which the fitness audience is saturated with and discounts.

- **Likelihood:** Medium that someone asks; near-certain *eventually* if framing is left ambiguous.
- **Damage:** High per incident Ã¢â‚¬â€ a small authenticity fudge is disproportionately expensive when the entire moat is "we don't fudge."

**Cheap mitigation (zero hours Ã¢â‚¬â€ it's labeling discipline):**
- **Label the relationship in-frame or in-caption, every time.** One honest line does it: "my partner built this and I'm its first (and harshest) tester" Ã¢â‚¬â€ which is *stronger* content than a founder demo, because "the builder's own household can't get a softball read" is the honesty story in miniature. The existing UGC rules in LAUNCH_KIT (never fake a reaction; if the read misses, show that too) already carry the rest.
- **The founder owns the text-native channels as himself** Ã¢â‚¬â€ Reddit post, X thread, PH launch, support replies, build-in-public Ã¢â‚¬â€ where writing is the medium and no camera is needed. Faceless-but-real formats (screen recording + voiceover, read-of-my-own-reel walkthroughs) cover video without borrowing a face.
- **Pre-write the answer** to "is this your app?" for her comments: "Nope Ã¢â‚¬â€ my partner built it, I'm the first user. Which is why my reads are extra brutal." First-reply, never after a screenshot forces it.

**Tripwire:** any comment questioning who's behind the app or whether the reaction is paid Ã¢â€ â€™ truthful pinned reply within the hour. If a video's comment section tilts to authenticity questions rather than product questions, that format is burned Ã¢â‚¬â€ go back to founder-voice screen recordings for the next two posts.

---

## 9. Fitness creators distrust text-heavy critique Ã¢â‚¬â€ and the wedge gets *more* silence

**What goes wrong.** Two stacked problems in the chosen wedge:

1. **Culture:** fitness creator culture is visual, kinetic, and before/after-driven; a multi-paragraph AI critique reads like an English teacher grading a deadlift. The CREATOR_XP_AUDIT persona (skeptical 24-year-old fitness creator, one upload before deciding) already flagged the mechanics: judge-first ordering, prose-only copy, a cramped action row on the exact CTA.
2. **Mechanics (the sharper risk):** many fitness reels are music-driven demos with little or no speech. The grounding gate is deliberately transcript/caption/thumbnail-primary because VLM perception is noisy Ã¢â‚¬â€ and is *known* to be weaker on music-driven and female-presenting reels (the documented reason the gate is built that way). Less transcript Ã¢â€ â€™ less verifiable ground Ã¢â€ â€™ **the wedge niche is structurally the most likely to receive suppressed reads**. Worst case, the GTM sends fitness creators to an app that systematically tells fitness creators the least Ã¢â‚¬â€ which then feeds risks #3 and #4.

- **Likelihood:** Medium-High for the culture mismatch; the suppression skew is an empirical question that must be answered *before* launch, not during.
- **Damage:** High Ã¢â‚¬â€ a wedge that under-serves its own niche fails quietly (the STRATEGY tripwire "WAU < 50 at month 3" fires months after the cause).

**Cheap mitigation:**
- **Pre-launch spot-check (half a day, decisive):** run 20 music-only / low-speech fitness reels through the live pipeline; compare suppression% and lever quality vs. 20 talking-head fitness reels. If music-only suppression is > 1.5x, the fitness accuracy sprint (currently Month 4-6) has a pre-launch slice: tune what the gate accepts as visual-only grounding for fitness patterns (form cues, rep pacing, before/after payoff placement Ã¢â‚¬â€ which the intent-guard work already recognizes as deliberately backloaded).
- **Ship the audit P0s that de-text the read** before creator outreach: coach-first ordering (What's working before the fix), checklist-format copy ("Ã¢ËœÂ 0:07 Ã¢â‚¬â€ Ã¢â‚¬Â¦"), un-crammed action row. Same critique, half the perceived text.
- **Lead outreach with the binary artifact, not the prose:** the revision-loop verdict (**Fixed / Still there**) is the one output that speaks fitness culture natively Ã¢â‚¬â€ it *is* a before/after. DMs and demo videos should show the re-check receipt, not a wall of notes.
- **Per-niche instrumentation (the must-have):** `Upload.niche` is already selected in kpis.py but never broken out. Add suppression%, helpful%, and D7 **by niche** to `/tools/kpis` (~1h Ã¢â‚¬â€ the data is in hand). STRATEGY.md already commits to "instrument helpful% and D30 BY NICHE from day 1"; the code doesn't do it yet.

**Tripwire:** fitness `suppression_pct` > 1.5x the all-niche average, or fitness `helpful_pct` < 50% while other niches sit Ã¢â€°Â¥ 60% Ã¢â€ â€™ pause fitness outreach, run the 20-reel diagnostic, and be genuinely willing to let the data move the wedge to food (the STRATEGY already licenses this at Month 4 Ã¢â‚¬â€ the per-niche numbers just have to exist to invoke it).

---

## The tripwire page (tape this to the KPI ritual)

Check `/tools/kpis?key=Ã¢â‚¬Â¦` daily during launch week, then Mon/Thu. Thresholds:

| Signal | Where | Threshold | Action |
|---|---|---|---|
| `uploads.ungated` | kpis | **> 0** | Halt all outbound; fix the gate today (silent-degradation alarm) |
| `uploads.suppression_pct` | kpis | > 20% weekly | Investigate before any promotion |
| Fitness vs. all-niche suppression | kpis (after per-niche patch) | > 1.5x | Pause fitness outreach; run 20-reel diagnostic |
| `feedback.by_reason.not_in_my_reel` | kpis | > 10% of weekly taps | Treat as fabrication incident: reproduce, fix, consider 48h postmortem post |
| `feedback.helpful_pct` | kpis | < 50% weekly | Stop scaling outreach; 5 user interviews first |
| App Store rating | App Store Connect (daily glance, launch week) | < 4.0 with < 30 ratings | Pause outbound; personally ask 5 provably-happy users to rate |
| DM reply rate | manual tally | < 10% over 20 DMs | Rewrite template before DM #21 |
| Any IG "action blocked" | founder's phone | once | 48h full stop on all IG actions |
| Reddit post health | thread | removed or < 50% upvotes in 1h | Self-delete; modmail the next sub instead |
| Upload pace | `uploads.last_7d` + provider dashboard | > ~50 fresh/hr or > $15/day spend | Circuit breaker decision: raise cap or hold |
| Read latency / failures | events (after latency event added) | p50 > 4 min or `no_read` climbing | Flip "delayed reads" banner; stop intake if provider is down |
| Reel-grab log | Railway logs, weekly skim | unknown IP / non-tester URL / > 10/day | Rotate `API_TOOLS_KEY` same day |

## Four engineering asks this red-team requires (Ã¢â€°Ë† 1.5 days total, before the first outbound post)

1. **Per-niche KPI breakdown** (suppression%, helpful%, D7 by `Upload.niche`) in kpis.py Ã¢â‚¬â€ the wedge tripwire is blind without it. (~1h)
2. **Channel attribution:** accept `?src=` on the web app, stamp it into signup `Event.props`, surface in `events_7d`. (~1h)
3. **Global daily read circuit breaker** (`MAX_FRESH_READS_PER_DAY=300`) + friendly capacity state + provider spend alerts/caps. (~4h)
4. **Split `API_TOOLS_KEY`** into tester (reel-grab) vs. owner (kpis/users/uploads) keys, and rotate the tester key per batch Ã¢â‚¬â€ one shared key currently exposes the PII endpoints to anyone a tester forwards a URL to. (~30m)

Plus one scheduling change: **pull the multi-vendor A/B and a transcription fallback forward from Month 2 to pre-launch week** Ã¢â‚¬â€ #7 is the only risk on this list that can zero out launch week entirely, and its mitigation is already scoped, just scheduled too late.

---

**Sources:** [Instagram DM Limits 2026 Ã¢â‚¬â€ Inro](https://www.inro.social/blog/how-many-direct-messages-can-you-send-on-instagram) Ã‚Â· [Instagram DM Limits: Daily Caps Ã¢â‚¬â€ Flowgent](https://flowgent.ai/blog/instagram-dm-limits-how-many-messages-you-can-send-daily) Ã‚Â· [Instagram DM Limits & Rules 2026 Ã¢â‚¬â€ InstantDM](https://instantdm.com/blog/instagram-dm-limits-rules-2026-the-ultimate-account-safety-guide). Internal grounding: `api/routers/upload.py` (per-IP caps, in-memory windows, suppression auto-retry), `api/routers/tools.py` (reel-grab gating, shared key, PII endpoints), `creative_director/storage/kpis.py` (all dashboard fields incl. the `ungated` alarm), `docs/STRATEGY.md`, `docs/LAUNCH_KIT.md`, `docs/CREATOR_XP_AUDIT.md`.