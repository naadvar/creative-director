# Creator-experience audit (2026-07-01)

_Four agents walked the real screens as a skeptical 24yo fitness creator (8K
followers, edits in CapCut on phone, gives the app ONE upload before deciding).
Excludes everything already queued (push, emails, telemetry, share CTA, Wabi
glow-up, Ideas feature). Every claim cites a file._

## The five moments most likely to lose a creator (ranked)

1. **The wait can silently "hang."** No timeout/error fallback if polling stalls —
   the client polls `/upload/{job_id}` every 3s forever (UploadPage.tsx:197-209);
   and the stage stepper's message→stage mapping falls through to stage 0 on any
   unrecognized backend message, so the progress UI can *regress or freeze*
   (UploadPage.tsx:54-61). First-session bounce risk, and the creator never knows
   anything went wrong.
2. **The lever's action row is cramped on phones.** Copy / Helpful / Re-upload /
   Jump-to-timestamp share a flex row that wraps awkwardly or pushes actions
   off-screen at narrow widths (CraftRead.tsx:206-267) — the product's #1 CTA is
   "scroll to find."
3. **Praise is visually subordinate to the flaw.** "What's working" renders AFTER
   "Fix this first" (CraftRead.tsx:271-283) — reads as judge-first, coach-second.
   For a debut creator that's the churn-silently moment.
4. **The read → editor bridge is thin.** Copy copies plain prose only — no
   checklist format, no copy-all-blind-spots (CraftRead.tsx:209-213); fix language
   mixes critique-speak with editor-actionable phrasing; player↔note sync requires
   scrolling up/down between the note and the scrubber (VideoPage.tsx:111-146).
5. **Early states look abandoned, not accumulating.** One read in the Library grid
   under "watch your craft sharpen" looks dead (MyUploadsPage.tsx:104-118); the
   Growth empty state has no progress-toward-3-reads affordance and no unlock
   celebration (MyDnaPage.tsx:149-161); "No grounded read" label is opaque and
   mildly accusatory (MyUploadsPage.tsx:87).

## P0 — build this week (all frontend, no backend risk)

| # | Fix | Where | Effort |
|---|---|---|---|
| 1 | Upload resilience: max-wait with an honest "taking longer than usual" state + retry guidance; stage mapping falls back to the CURRENT stage (never regress/freeze) | UploadPage.tsx | S/M |
| 2 | Coach-first read order: verdict → What's working (visual weight up) → Fix this first → blind spots | CraftRead.tsx | S |
| 3 | Un-cram the lever action row at 380px (stack the buttons cleanly) | CraftRead.tsx | S |
| 4 | Copy = a paste-ready checklist ("☐ 0:07 — …" per fix), not prose | CraftRead.tsx | S |
| 5 | Early-state warmth: Growth empty state gets a "2 of 3 reads" progress affordance (mirror the post-read CTA), a small fingerprint-unlock moment, and "No grounded read" → "Watched closely — no single fix to push" | MyDnaPage/MyUploadsPage | S/M |

## P1 — next

- Player↔note sync on mobile: floating timestamp chip / sticky mini-player while
  scrolling the read (M/L)
- Editor-vernacular pass on fix phrasing (prompt change — validate via the QA
  scripts, don't freehand the gate) (M)
- Interactive checklist mode (checkboxes persisted per read; feeds the re-check
  loop) (M)
- "Your first read" framing for a single-item Library (S)

## Do not do
- Don't soften the honesty to fix tone — fix ORDER and visual weight, not content.
- Don't add a fake progress bar to the wait — make the stall states honest instead.
- Don't bury the one-lever hierarchy under a checklist of everything.
