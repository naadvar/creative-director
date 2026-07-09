# Launch Playbook — pre-share gaps, outreach + feedback, creator-lens roadmap

*2026-07-09. Companion to STRATEGY.md (wedge/pricing) and LAUNCH_KIT.md (assets).
Part 1 is what to build/fix BEFORE sharing widely; Part 2 is how to reach people
and learn from them; Part 3 is the long-term product view through a creator's eyes.*

---

## Part 1 — Close these gaps before strangers arrive

Ranked. Effort tags assume Claude does the building. Items marked ✅-adjacent are
mostly wiring, not new product.

### P0 — compliance & the only owned channel (do first)

1. **Account deletion (App Store rule 5.1.1(v))** — apps with account creation
   must let users delete the account in-app. We have delete-upload but no
   delete-account. One endpoint (purge User + Uploads + files + events) + a
   button in settings. *Risk if skipped: removal from sale on a metadata review.*
   (day)
2. **Domain + Resend → turn on email** — the read-ready + welcome emails are
   fully wired and inert. Buy domain, verify in Resend, set env. Two fixes while
   wiring: send for suppressed reads too ("here's what looked good"), and only
   email when the read wasn't viewed within ~10 min (Event table already logs
   read_viewed) so engaged users aren't spammed. Add List-Unsubscribe +
   support@ reply-to. (hours once domain exists)
3. **support@domain everywhere** — replace the personal gmail in App Store
   support URL + app. (hours)
4. **Purge the ~10 @example.com probe accounts** so KPIs read true before you
   start watching them daily. (hours)
5. **Provider-balance tripwire** — the July outage class (DeepInfra credits) is
   silent. Nightly check hits the provider balance endpoint + the UNGATED KPI;
   emails you at a threshold. (hours)

### P1 — first-session survival (the $0.05 you already spent)

6. **Resume in-flight job on return** — persist {job_id, video_id} to
   localStorage/Preferences on submit; on app open, if a job exists poll once →
   "Your read finished — view it" banner, or re-enter the progress view. Kills
   the "closed the tab = thinks it failed" bounce. (hours)
7. **Example read before sign-in** — iOS opens to sign-in; a stranger can't see
   value before handing over an account. One "See an example read" link on the
   sign-in screen → a canned corpus read. (hours–day)
8. **Rating prompt at the peak moment** — SKStoreReview after a "✓ Fixed"
   verdict or a helpful-vote, capped by Apple's own throttling. Early stars
   decide App Store search rank. (hours)

### P2 — the comeback loop (reads 2–5 are where the product proves itself)

9. **"Open fix" card on the New tab** — an upload is an open fix when its read
   is grounded, has a real lever, and no later upload re-checks it (all fields
   exist on Upload). Card: "Fixed *0:07 — hook text unreadable* on Leg-day reel?
   Re-upload to check." → /analyze?prior=. The strongest comeback mechanic
   currently hides inside one page. (day)
10. **Milestone ladder to 5 + self-serve Ideas unlock** — today the ladder ends
    at read 3 (trend). Flip SHOW_IDEAS=true but gate server-side at 5 grounded
    reads with the honest locked state ("Ideas need enough of your own reads").
    Every read 1→5 now has a named payoff: 1 fingerprint, 3 trend, 5 ideas —
    and the dark feature ships itself exactly on your unlock criterion. (day)
11. **iOS local notification for the re-check nudge** — after the first grounded
    read, offer "Editing later? Get a nudge in 3 days." Local notifications
    (no APNs, no server) schedule on-device; tap deep-links to ?prior=. Cancel
    on re-check or delete. Defer real push infra to month 2. (days)
12. **Fixed ✓ badges in Library + "2 fixes verified" line in Growth** — the
    verifier's best moment currently renders once on one page. Library becomes
    the scoreboard of loops closed. (hours)
13. **Hourly nudge worker** — one key-gated endpoint a Railway cron hits:
    (a) read-ready catch-up emails, (b) day-3 open-fix emails, max one nudge
    per user per 7 days. Covers web users who never granted notifications. (day)

### Deliberately NOT before sharing
- Paywall (free is the growth fuel; triggers in STRATEGY.md stand)
- APNs/OneSignal push (local notifs + email cover both real gaps)
- Android, Product Hunt, share cards (see Part 3 — NEXT)

---

## Part 2 — Outreach + feedback: the first 100 real creators

**Positioning that does the selling: "the AI critic that refuses to promise
virality."** Every template below leads with honesty because it is the single
most differentiated (and most disarming) thing about the product. Never critique
someone's reel unsolicited — offer the read, let them opt in.

**Founder budget: ≤ 90 min/day.** Feedback > installs until read-2 rate is known.

### Week 0–1: the warm 20
- Personally ask 20 people one hop away (testers, friends' creator friends,
  gym acquaintances): 2 uploads + one 15-min call each. Script: "It's free, I
  need brutal feedback, and it will never promise you views — it critiques
  craft like an editor would."
- Sister/gf shoots Video 1 per the LAUNCH_KIT shot list; post to a fresh IG +
  TikTok account for the app.

### Weeks 1–4: channels, quotas, templates

| Channel | Daily/weekly effort | The move | Kill signal |
|---|---|---|---|
| **IG DMs (fitness 2k–50k)** | 10–15 DMs/day, 30 min | 5 genuine comments to warm the account first. DM: "Hey {name} — loved the {specific reel detail}. I built an AI that critiques reel *craft* (it never predicts virality — it just reads your actual frames and flags what an editor would). Free while I test with fitness creators. Want a read of your latest?" | reply rate <10% after 100 DMs, or restricted for spam → stop, rework |
| **Reddit (r/InstagramMarketing, r/CreatorEconomy, shorts/fitness-creator subs)** | 2–3 posts/wk, 20 min/day | Value-first only: post anonymized teardown threads ("I analyzed 50 fitness reels — the 5 recurring craft mistakes, with timestamps"). Tool in profile + comments only when asked. Obey each sub's self-promo rules to the letter. | post removed twice in a sub → leave it |
| **X/Threads build-in-public** | 1 post/day, 10 min | Real numbers, real bugs, the honesty angle ("today my own app told me my hook was unreadable"). Compounding credibility, low direct installs. | none — cheap |
| **Discord/Slack creator + editor communities (3–5)** | 15 min/day | Be useful for a week, then share in show-your-work channels. Editors are the harshest and best judges of note quality. | — |
| **Micro-influencer barter (5–10 fitness creators 10–50k)** | 2 asks/wk | Free Pro-for-life + featured before/after (with consent) for one honest story mention. | — |
| **Product Hunt** | — | **Not yet.** A spike on a funnel without proven read-2 retention is wasted. Revisit when Part 1 items 9–13 are live and read-2 ≥ 30%. | — |

Sequencing: W1 warm 20 + instruments → W2 DMs + first teardown post → W3 video
live + communities → W4 KPI review, drop the weakest two channels, double the best.

Hard anti-spam rules: every DM names them + one specific reel detail; never
batch-paste; log every touch in a sheet (handle, date, reply?, uploaded?, read-2?).

### Feedback collection (the actual point of the first 100)

**Instruments (mostly already live):** note-level helpful / not-useful /
not-in-my-reel taps, events, /tools/kpis. Add exactly one: a post-read one-tap
**"Will you change anything from this read?" yes / no / already posted** — it's
the intent-to-apply signal that predicts both retention and the re-check funnel.

**Interviews: 3–5/week, 20 min, $10 gift card or Pro-for-a-year.**
Recruit every warm-20 user and any DM convert with 2+ uploads. Guide:
1. "Walk me through your last posted reel, start to finish." (map their real
   workflow — where would a read actually slot in?)
2. Run a live read of their reel. Watch their face. Then: "Read each note out
   loud — is it real or generic?" (note-level truth, the thing judges can't tell you)
3. "What would you literally do next with this?" (apply intent)
4. "It'll be $9.99/mo eventually — what would it need to do?" then the Sean
   Ellis question: "How would you feel if it disappeared — very disappointed,
   somewhat, or fine?" (only "very" counts)
5. "Who are two creators you'd send this to?" (referral engine — ask every time)

**Log:** one docs/FEEDBACK_LOG.md, one dated entry per interview, tagged by
feature area. Patterns, not anecdotes: nothing gets built until 3 independent
people hit the same wall.

**Friday 30-min founder ritual** (/tools/kpis + the sheet):
read-2 rate, D7 cohort, suppression %, helpful %, top "not in my reel" notes,
DM funnel (touch→reply→upload→read-2) → pick ONE build priority for next week.

**Decision gates:**
- Paywall on: D30 ≥ 20% or COGS > $150/mo (unchanged from STRATEGY.md)
- Ideas unlock: automatic at 5 grounded reads (ships in Part 1 #10)
- Pivot-alarm: after nudges live for 4 weeks, if < 25% of read-1 users ever do
  read 2 → the loop isn't landing; stop outreach, fix product
- Channel kill: see table

---

## Part 3 — Long-term roadmap through a creator's lens

The organizing insight: a creator's life is a loop — **plan → shoot → edit →
post → wonder what happened → plan again**. Today the product only enters
after "post" (or at best before it). Every stage the read reaches is a new
reason to open the app, and every verified outcome deepens the dataset moat
(advice→outcome pairs nobody else has).

### NOW (pre-100 users) — Part 1 items: finish the post→re-check loop.

### NEXT (100 → 1,000)

1. **Draft reads (pre-post check)** — upload the cut *before* posting; read
   flags fixable issues while the editor is still open. Moves the product from
   post-mortem to part of the workflow — the single biggest jobs-to-be-done
   upgrade. Bonus: draft→final pairs are outcome data. Guardrail: same
   craft-only voice; never "this will do numbers."
2. **Shot-list from your DNA** — extends the dark Ideas feature into planning:
   "your recurring gap is illegible text → your next-shoot checklist." Uses the
   existing idea_id → upload → read → verify chain, closing the FULL loop.
3. **Skill arc in Growth** — per-change_type trajectory from data we already
   store: "text legibility: flagged 4× in your first 5 reels, 0× in your last
   5." The honest version of gamification; the strongest pay-to-keep feature.
4. **Audio brief** (already queued) — the read as a 60-second listen for the
   edit chair / commute.
5. **"Fixed ✓" share card** — before/after frames + the note that got fixed,
   creator-initiated, consent-first. The only share artifact that spreads
   WITHOUT a performance claim — it brags about craft, not views.
6. **Platform-aware framing for TikTok/Shorts** — prompt-level (cheap): same
   read, platform-correct vocabulary; widens the wedge without new corpus work.
7. **APNs push** — once local-notification re-check nudges prove conversion.
8. **Paywall/Pro** — on the standing triggers, never before read-2 economics
   are understood.

### LATER (post-PMF)

9. **Meta OAuth ingestion** — auto-pull their reels + real outcomes. This is
   the moat accelerant: verified advice→outcome pairs at scale. Outcomes feed
   the DATASET, never individual predictions (honesty line). Pre-req: encrypt
   ConnectedAccount tokens (standing item).
10. **Coach/agency mode** — the creator-coach persona reviews 30+ client reels
    a month: multi-client workspaces, batch triage, white-label client reports.
    First B2B tier (~$49/mo) and the highest willingness-to-pay in the pipeline.
11. **Craft portfolio for UGC creators** — a public "craft-certified" reel page
    brands can check. UGC creators' income depends on the reel itself, not
    reach — they are the persona most aligned with our no-virality stance.
12. **Skill drills** — "shoot the same hook 3 ways, upload, the read picks the
    cleanest and says why." Practice mode; deliberate skill-building on your
    own recurring gap.
13. **Android** — only after the iOS loop retains.

### Never (the contract)
- Virality/performance prediction, trend-chasing ideation, follower promises,
  engagement-bait suggestions, auto-posting, buying/pod schemes. Each one would
  spend the only brand asset we have: the app never lies about what it can know.

### The spine bet
Everything above serves one flywheel: **more verified fix-outcomes per creator
per month**. Draft reads create more read-moments, DNA shot-lists create more
planned attempts, re-check nudges create more verdicts, OAuth creates outcome
ground-truth, and the skill arc makes the accumulation visible enough to pay
for. The dataset of "this specific change, verified landed, in this niche" is
the thing a buyer can't rebuild without reliving the whole journey — protect it
with every roadmap choice.
