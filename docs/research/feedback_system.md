# Feedback Collection System Ã¢â‚¬â€ Founder Playbook

*Everything here is sized for one person. Total steady-state cost: ~3.5 h/week + ~$200/mo in interview incentives + ~2 dev-days of one-time instrument work. Every mechanism respects the honesty contract: first-party data only, no session recordings, no third-party analytics SDKs, no dark-pattern surveys.*

---

## 1. Instruments

### 1a. What already exists (use it, don't rebuild it)

| Instrument | What it captures | Where it lives |
|---|---|---|
| **Lever feedback** ("Was this fix helpful?") | `helpful` / `not_useful` on the biggest-opportunity lever | `CraftRead.tsx` Ã¢â€ â€™ `NoteFeedback` rows in writable `userdata.db` (survives deploys) |
| **Per-note dismissal** | `not_useful` / `not_in_reel` on any blind-spot note Ã¢â‚¬â€ `not_in_reel` is a **fabrication label**, the single most valuable tap in the product | `POST /videos/{id}/note-feedback` Ã¢â€ â€™ `NoteFeedback` |
| **Server events** (since 2026-07-04 Ã¢â‚¬â€ no backfill exists) | `login(method, new_user)`, `upload_started(niche, revision, idea)`, `read_completed(grounded, suppressed, revision_state)`, `read_deduped`, `read_failed(error)`, `read_viewed`, `upload_deleted` | `creative_director/storage/telemetry.py` Ã¢â€ â€™ `events` table |
| **Frontend tap events** (whitelisted) | `app_opened`, `copy_checklist`, `copy_caption`, `share_tapped`, `idea_planned` | `POST /events` (`api/routers/events.py`) |
| **Revision verdicts** Ã¢â‚¬â€ *the moat dataset* | `prior_video_id` + `revision_verdict` = `fixed` / `still_there` / `cant_verify` per re-check | `uploads` table |
| **Idea feedback** (dark, `SHOW_IDEAS=false`) | `helpful` / `not_for_me` per generated idea | `creator_ideas.feedback` |
| **KPI dashboard** | WAU/MAU, signups, uploads funnel, suppression %, **`ungated` alarm** (fact-check gate didn't run Ã¢â‚¬â€ must be 0), revision-loop counts, helpful %, 7-day event counts, 8 weekly cohorts with D1/D7 | `GET /tools/kpis?key=<API_TOOLS_KEY>&format=text` Ã¢â‚¬â€ works from your phone |
| **Lead list / read debug** | Per-user signups, last login, upload counts; last-N stored reads | `/tools/users`, `/tools/uploads` (key-gated) |
| **Feedback triage report** | Aggregates NoteFeedback into three action lists: `not_in_reel` Ã¢â€ â€™ grounding-gate eval set, `not_useful` Ã¢â€ â€™ prompt-tuning backlog, `helpful` Ã¢â€ â€™ lever shapes to keep | `python -m scripts.feedback_report [days]` |

**Metric definitions (write these down once, read them the same way forever):**
- `helpful%` = helpful / all feedback taps **including silent dismissals** Ã¢â‚¬â€ it will read low; that's fine, keep the definition stable.
- `suppression%` = suppressed / (grounded + suppressed). Healthy band: **5Ã¢â‚¬â€œ25%**. Below 3% Ã¢â€ â€™ audit the gate (too loose?). Above 30% Ã¢â€ â€™ users see silence too often; it's a UX problem before it's a model problem.
- `ungated > 0` = the fact-check gate never ran on a read that shipped. This is a **same-day fix**, always.

### 1b. Three additions to build (Ã¢â€°Ë†2 dev-days total)

**Addition 1 Ã¢â‚¬â€ Post-read PMF pulse (one tap, Sean Ellis question).** ~half a day.
- **Trigger:** shown once on the read page after a user's **3rd grounded read**; re-asked at most once per user per 30 days; **never after a suppressed read** (don't ask "how'd we do?" right after saying nothing).
- **Copy:**
  > *"One quick one Ã¢â‚¬â€ if Reel Reads disappeared tomorrow, how would you feel?"*
  > `[Very disappointed]` `[Somewhat disappointed]` `[Fine, honestly]`
  The third option is deliberately in-brand.
- **Implementation:** three new whitelisted event names Ã¢â‚¬â€ `pmf_very`, `pmf_somewhat`, `pmf_fine` Ã¢â‚¬â€ through the existing `POST /events` (no schema change; add to `_ALLOWED` in `events.py`).
- **Metric:** `PMF% = very / (very + somewhat + fine)`. The classic threshold is **40%**. This becomes an input to the paywall gate (Ã‚Â§3).

**Addition 2 Ã¢â‚¬â€ "Did you try the fix?" follow-up.** ~1 day. This is the highest-leverage one: it measures the gap between *"helpful" (polite)* and *"acted on it" (real)*, and it funnels users into the revision loop, which is the moat.
- **Trigger:** on the next `app_opened` Ã¢â€°Â¥ 48h after a grounded read that had a lever; one card, one pending ask at a time, asked once per read ever.
- **Copy:**
  > *"Tuesday's read pointed at a fix at 0:07 Ã¢â‚¬â€ did you get to it?"*
  > `[Made the edit Ã¢â€ â€™ Re-check it]` (deep-links straight into the revision re-upload for that read)
  > `[Not yet]`
  > `[Chose not to]` Ã¢â€ â€™ optional one-line "what made you skip it?" (free text Ã¢â€ â€™ `NoteFeedback` with reason `fix_rejected`)
- **Events:** `fix_applied` / `fix_pending` / `fix_rejected` (whitelist them, `video_id` attached).
- **Metric:** **fix-adoption% = applied / (applied + rejected)**, ignoring pendings. This is the truth-serum version of helpful%.

**Addition 3 Ã¢â‚¬â€ Per-niche + D30 cuts in `kpis.py`.** ~half a day, zero user-facing surface. Join `NoteFeedback.video_id Ã¢â€ â€™ uploads.niche` to get **helpful% by niche**; add **D30 to the weekly cohorts**; add **reads/uploader/week**. STRATEGY.md already demands "helpful% and D30 by niche from day 1" Ã¢â‚¬â€ the dashboard doesn't cut either yet, and the month-4 wedge-switch decision is impossible without them.

### 1c. Explicitly refused
- **Session recordings / heatmaps** Ã¢â‚¬â€ privacy violation for a product whose brand is trust; the interview program's watch-them-use segment covers the same need with consent.
- **Third-party analytics SDKs** (Mixpanel, PostHog cloud, etc.) Ã¢â‚¬â€ the first-party `events` table is enough at this scale, and "no third parties" is a marketable privacy fact.
- **Star ratings, multi-question in-app surveys, exit-intent popups** Ã¢â‚¬â€ each is a tax on the read experience for data you won't act on.

---

## 2. User Interview Program

### Who to recruit (three pools, in priority order)
1. **One-and-done churners** Ã¢â‚¬â€ 1 upload, no activity for 7 days (pull from `/tools/users`). Most valuable and hardest to book; over-ask this pool 2:1.
2. **Active users** Ã¢â‚¬â€ 2+ uploads (same list). Easiest to book; watch for politeness bias.
3. **Target creators who haven't signed up** Ã¢â‚¬â€ the fitness-DM list from the launch kit. Use for positioning/channel questions, not product-detail questions.

### Recruiting scripts
**Active user / churner (DM or email, once Resend is live):**
> Hey [name] Ã¢â‚¬â€ I'm the founder of Reel Reads (the app that read your reel [last week]). I'm doing 20-minute calls with early users to find out where the read was wrong or useless Ã¢â‚¬â€ the harsh version is the useful version. $25 gift card for your time, and I'll personally re-review any reel of yours live on the call. Any of these times work? [3 slots]

**Churner variant, add one line:** *"You uploaded once and didn't come back Ã¢â‚¬â€ that's exactly the story I need to hear. No hard feelings, I promise."*

**Incentive:** $25 gift card (Amazon/Starbucks) per completed call. Budget **$200Ã¢â‚¬â€œ250/mo**. Don't pay in Pro subscriptions Ã¢â‚¬â€ the product isn't priced yet, and paying with the thing you're asking them to value is circular.

**Cadence:** **2/week** in months 1Ã¢â‚¬â€œ2 (hits STRATEGY's "5 recorded interviews" in week 4), ramping to **3/week** in months 2Ã¢â‚¬â€œ3 during the fitness accuracy sprint (target: 20Ã¢â‚¬â€œ30 recorded fitness sessions). Yield planning: 5 asks Ã¢â€ â€™ 1Ã¢â‚¬â€œ2 booked, so send 8Ã¢â‚¬â€œ10 asks/week. Pause rule: if 3 consecutive interviews produce zero new insights, drop to 1/week until something changes (new feature, new cohort, new niche).

### The 20-minute guide

**0:00Ã¢â‚¬â€œ2:00 Ã¢â‚¬â€ Setup.** Ask to record (consented recording only). Say verbatim: *"The only way this call fails is if you're polite. I make money by finding out what's wrong."*

**2:00Ã¢â‚¬â€œ5:00 Ã¢â‚¬â€ Context (past behavior only, no hypotheticals).**
- "Walk me through the last time a reel underperformed. What did you actually do that day?"
- "What have you **paid for** in the last 12 months to make your content better Ã¢â‚¬â€ apps, presets, a coach, a course?" *(Payment history is the best predictor of willingness to pay. "Nothing, ever" is a signal.)*

**5:00Ã¢â‚¬â€œ11:00 Ã¢â‚¬â€ Watch them use it.** Have them upload a real draft live. **Say nothing for 3 minutes.** Watch for: where they squint (confusion), where they nod (recognition), whether they scroll past "What's working," whether they find the Copy/Helpful/Re-upload row (the XP audit flagged it as cramped on phones), what they do at the timestamp. Then: "Talk me through what you just read Ã¢â‚¬â€ what would you actually change in CapCut tonight?"

**11:00Ã¢â‚¬â€œ17:00 Ã¢â‚¬â€ The separator questions.** Each has a "listen for":

| Ask | Polite-nice answer | Would-pay answer |
|---|---|---|
| "What's the most **wrong** thing the read said?" | "Nothing really, it was great" | A specific note + timestamp (also: log any fabrication claim Ã¢â€ â€™ gate eval set) |
| "You saw the fix at [t]. Will you make that edit? When?" | "Yeah probably at some point" | A day. *(Then verify in telemetry next week Ã¢â‚¬â€ did they actually re-upload?)* |
| "If this cost **$9.99/month starting tomorrow**, walk me through what you'd honestly do." | "I'd think about it" | Either "cancel Ã¢â‚¬â€ because X" (gold) or "pay Ã¢â‚¬â€ because it replaced Y" (gold) |
| "What would this have to do for $9.99 to be a no-brainer?" | Feature wishlist recital | One concrete job tied to their workflow |
| "Who's one creator friend you'd send this to Ã¢â‚¬â€ and would you send it **right now**, while we're on the call?" | "Sure, I'll share it around" | They actually pull out their phone. Count sent-on-call as the metric. |
| "What would make you delete the app?" | "Nothing comes to mind" | A specific fear ("if it ever makes something up about my reel") Ã¢â‚¬â€ this is your churn model |

**17:00Ã¢â‚¬â€œ20:00 Ã¢â‚¬â€ Close.** Sean Ellis question verbally (same three options as the in-app pulse Ã¢â‚¬â€ verbal answers cross-check the in-app data). Then: "What should I have asked that I didn't?"

### Logging (15 minutes after each call, no more)
One entry per interview in `docs/interviews/LOG.md`:

```
## 2026-07-14 Ã¢â‚¬â€ @handle (fitness, 12K followers, 3 reads)
PMF: somewhat | Price: "would pay if DNA showed month-over-month proof" | Sent-on-call: yes
Top friction: didn't realize re-upload = re-check (thought it was a new read)
Fabrication claims: none
Promised action: re-edit hook cut by Friday Ã¢â€ â€™ VERIFY IN TELEMETRY [ ]
Best quote: "every other tool feels like a slot machine; this feels like my editor"
Tags: [PRICE] [REVISION-UX]
```

Tags: `[FAB]` `[PRICE]` `[RETENTION]` `[UX]` `[WEDGE]` `[CHANNEL]`. In the weekly review, count tag frequencies; three interviews with the same tag = backlog item. **Always check the "promised action" box against telemetry the following week Ã¢â‚¬â€ the promise-vs-behavior delta is your calibration for everything else they said.**

---

## 3. Decision Gates

Every gate names its metric source. Interview data (Ã‚Â§2) can *accelerate* a build decision but never *substitute* for a telemetry threshold.

### Build gates

| Decision | Trigger Ã¢â‚¬â€ build when ALL are true | Measured where |
|---|---|---|
| **Push notifications** | Already committed Ã¢â‚¬â€ ship in weeks 2Ã¢â‚¬â€œ3 while the launch cohort is active. No gate. | Ã¢â‚¬â€ |
| **Email nudges (Resend)** | Domain verified + key set. No metric gate Ã¢â‚¬â€ it's the only owned channel. | Ã¢â‚¬â€ |
| **Ideas unlock (`SHOW_IDEAS=true`)** | Ã¢â€°Â¥ 10 users with 5+ grounded reads each | `/tools/kpis` + `uploads` query |
| **Paywall flip ($9.99 Pro)** | 200 WAU **and** D30 Ã¢â€°Â¥ 20% **and** helpful% Ã¢â€°Â¥ 65% **and** in-app PMF% Ã¢â€°Â¥ 40% (n Ã¢â€°Â¥ 40 answers) **and** Ã¢â€°Â¥ 3 interviewees who unprompted said they'd pay | kpis + `pmf_*` events + interview log |
| **Android build** | iOS D7 Ã¢â€°Â¥ 25% | kpis cohorts |
| **Paid seeding ($300Ã¢â‚¬â€œ500 cap)** | Launch cohort D7 Ã¢â€°Â¥ 25% | kpis cohorts |
| **Coach/Agency tier** | Ã¢â€°Â¥ 5 **unprompted** coach/agency requests logged in interviews or support | interview log tag count |
| **TikTok support** | Fitness helpful% Ã¢â€°Â¥ 65% sustained 8 consecutive weeks | kpis per-niche cut (Addition 3) |
| **Niche #2 (food)** | Fitness helpful% Ã¢â€°Â¥ 70% and WAU Ã¢â€°Â¥ 400 (month ~9) | kpis |

### Kill / pivot / alarm gates

| Signal | Threshold | Action |
|---|---|---|
| `ungated` on dashboard | > 0 | **Same-day fix.** Reads shipping without the fact-check gate is the one existential product bug. |
| Fabrication rate | `not_in_reel` Ã¢â€°Â¥ 5% of feedback taps (n Ã¢â€°Â¥ 100), **or one substantiated public fabrication** | Freeze prompt changes; run gate eval (`scripts/tmp/retest_gate.py`); if public: fix + published postmortem within 48h |
| Launch-cohort D7 | < 15% | Stop ALL outbound; fix the first session (the XP-audit P0 list is the checklist) before spending another hour on growth |
| WAU at month 3 | < 50 | Freeze feature work; run 20 interviews; treat as positioning/channel problem, not product depth |
| helpful% | < 50% sustained 4 weeks at n Ã¢â€°Â¥ 100 | Read-quality sprint; tune via QA scripts, never freehand the gate |
| Fix-adoption% (Addition 2) | < 20% at n Ã¢â€°Â¥ 50 resolved asks | Advice is admired but not actionable Ã¢â‚¬â€ interview probe on fix phrasing / editor-vernacular (XP audit P1) |
| Wedge check (month 4) | Another niche beats fitness on **both** helpful% and D7, n Ã¢â€°Â¥ 30 uploads each | Switch the wedge. The playbook ports; only the target changes. |

---

## 4. The Weekly Founder Review (Sunday, 45 minutes)

Fixed appointment Ã¢â‚¬â€ same time weekly (e.g., Sunday 7pm). Output goes into a running `docs/WEEKLY_REVIEW.md`, one dated section per week, newest on top.

**Runbook:**

1. **(5 min) Pull the numbers.** `GET /tools/kpis?key=Ã¢â‚¬Â¦&format=text` (works from your phone). Paste the raw block into this week's section. Run `python -m scripts.feedback_report 7` and paste that too.
2. **(5 min) Fill the scorecard:**

   | Metric | This wk | Last wk | Target / band | Ã°Å¸Å¡Â¦ |
   |---|---|---|---|---|
   | WAU (north star) | | | Wk1 25 Ã¢â€ â€™ Wk4 55 Ã¢â€ â€™ Wk8 90 Ã¢â€ â€™ Wk13 150 | |
   | New signups (7d) | | | | |
   | Uploads (7d) / reads per uploader | | | Ã¢â€°Â¥ 1.5 reads/user/wk by month 3 | |
   | D7 Ã¢â‚¬â€ latest mature cohort | | | Ã¢â€°Â¥ 20Ã¢â‚¬â€œ25% | |
   | D30 (once Addition 3 lands) | | | Ã¢â€°Â¥ 15% (month 2) Ã¢â€ â€™ 18Ã¢â‚¬â€œ20% (month 3) | |
   | helpful% (7d, n=Ã¢â‚¬Â¦) | | | Ã¢â€°Â¥ 60% | |
   | `not_in_reel` count | | | ~0 Ã¢â‚¬â€ every row gets read | |
   | Suppression% | | | 5Ã¢â‚¬â€œ25% band | |
   | Re-checks Ã¢â€ â€™ fixed / still / can't | | | growing weekly (the moat) | |
   | Fix-adoption% | | | Ã¢â€°Â¥ 20% | |
   | PMF% running (n=Ã¢â‚¬Â¦) | | | 40% unlocks paywall math | |
   | `ungated` / `read_failed` | | | **0** / ~0 | |

3. **(10 min) Feedback triage.** Every `not_in_reel` row: watch the reel section it names; if the model really fabricated Ã¢â€ â€™ add to the gate eval set. Top `not_useful` patterns Ã¢â€ â€™ prompt-tuning backlog (validated via QA scripts only). Note the `helpful` lever shapes to keep.
4. **(5 min) Interview accounting.** Verify last week's promised actions against telemetry (did the "I'll re-upload Friday" person re-upload?). Update tag counts. Confirm 2 interviews are booked for the coming week Ã¢â‚¬â€ if not, send 5 recruiting asks *right now*, during the review.
5. **(10 min) Gate pass.** Read Ã‚Â§3 top to bottom. Any build gate triggered? Any alarm? A triggered gate is a *decision already made* Ã¢â‚¬â€ execute it, don't relitigate it.
6. **(5 min) Commit the week.** Write exactly three lines: **ONE product action. ONE growth action. What I am explicitly NOT doing.** If a line is missing, the review isn't done.
7. **(5 min) One honest paragraph.** What actually happened this week vs. what the plan said. This is the log a future raise, sale, or postmortem gets written from.

**Monthly deep version (first Sunday):** add 30 minutes Ã¢â‚¬â€ full cohort-curve pass (all 8 weeks), interview tag rollup, per-niche helpful%/D7 comparison against the wedge-check gate, and a COGS sanity check (reads Ãƒâ€” ~$0.05 vs. the $10/mo baseline).

**Standing red lines, any day of the week (don't wait for Sunday):** `ungated > 0` Ã¢â€ â€™ fix today. Substantiated fabrication complaint Ã¢â€ â€™ 48h fix + public postmortem. `read_failed` spike Ã¢â€ â€™ check `backend` logs before bed.

---

### Time budget (steady state)
| Activity | Weekly cost |
|---|---|
| Weekly review ritual | 45 min |
| 2 interviews + writeups + recruiting | ~2.5 h |
| Feedback-driven prompt/gate tuning | inside existing product time |
| **Total** | **~3.5 h/week** Ã¢â‚¬â€ fits alongside the 6 h/week marketing cap |
