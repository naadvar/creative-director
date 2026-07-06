"""Emit the judge workflow with artifacts embedded + a blind-shuffle key for captions."""
import json, random, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

A = json.load(open("scripts/tmp/pt_artifacts.json", encoding="utf-8"))
ideas = [i for i in A["ideas"] if "idea" in i]

# Blind caption sets: shuffle [ours1, ours2, baseline, real] -> labels A-D per reel.
random.seed(42)
blind_sets, key = [], {}
for c in A["captions"]:
    if "our_options" not in c:  # honest suppression — nothing to judge
        continue
    opts = []
    for j, o in enumerate(c["our_options"] or []):
        if isinstance(o, dict) and o.get("caption"):
            opts.append(("ours_" + (o.get("job") or str(j)), o["caption"]))
    if c.get("naive_baseline"):
        opts.append(("baseline", c["naive_baseline"]))
    opts.append(("real_posted", c["real_caption_they_posted"]))
    random.shuffle(opts)
    labels = "ABCDE"[: len(opts)]
    key[c["video_id"]] = {labels[i]: opts[i][0] for i in range(len(opts))}
    blind_sets.append({
        "video_id": c["video_id"],
        "what_the_reel_is": c["what_it_is"],
        "creators_past_captions_voice_reference": c["their_past_captions"],
        "candidates": {labels[i]: opts[i][1] for i in range(len(opts))},
    })
json.dump(key, open("scripts/tmp/pt_caption_key.json", "w", encoding="utf-8"), indent=1)

# ensure_ascii=True: IG captions/transcripts carry unicode control chars (U+2028,
# C1 controls) that break script embedding — escape everything to plain ASCII.
IDEAS_JSON = json.dumps(ideas, ensure_ascii=True)
CAPS_JSON = json.dumps(blind_sets, ensure_ascii=True)

script = '''export const meta = {
  name: 'pt-v12-judges',
  description: 'Adversarial judging of generated Ideas-from-DNA outputs and caption-as-remedy prototypes for the v1.2 ship decision',
  phases: [{ title: 'Judge' }],
}

const IDEAS = ''' + json.dumps(IDEAS_JSON) + ''';
const CAPS = ''' + json.dumps(CAPS_JSON) + ''';

phase('Judge')

const IDEA_SCHEMA = {
  type: 'object', required: ['judgments'],
  properties: { judgments: { type: 'array', items: { type: 'object',
    required: ['profile', 'concept', 'score', 'verdict', 'reason'],
    properties: {
      profile: { type: 'string' }, concept: { type: 'string' },
      score: { type: 'integer', minimum: 1, maximum: 5 },
      verdict: { type: 'string', enum: ['ship', 'meh', 'kill'] },
      reason: { type: 'string' },
    } } } },
}

const CAP_SCHEMA = {
  type: 'object', required: ['rankings'],
  properties: { rankings: { type: 'array', items: { type: 'object',
    required: ['video_id', 'best', 'worst', 'plausibly_the_creators', 'reason'],
    properties: {
      video_id: { type: 'string' },
      best: { type: 'string' }, worst: { type: 'string' },
      plausibly_the_creators: { type: 'array', items: { type: 'string' },
        description: 'labels that could plausibly be what this creator actually posted (voice match)' },
      reason: { type: 'string' },
    } } } },
}

const ideaJudges = [
  { key: 'creator-taste', brief:
    'You are a time-poor short-form creator in the stated niche deciding what to film this week. ' +
    'For EACH idea judge: would you actually be EXCITED to shoot this, or is it homework? score 1 (never) ' +
    'to 5 (grabbing my phone now). Judge taste and freshness, not correctness. Be harsh — creators are.' },
  { key: 'slop-null-test', brief:
    'You are a skeptic testing specificity. For EACH idea: could a generic chatbot given ONLY the niche name ' +
    '(no creator data) plausibly have produced this exact idea? If yes, that is slop -> kill. Score 5 = could ' +
    'ONLY come from this creator profile (cites their actual style/reels meaningfully), 1 = fully generic.' },
  { key: 'trust-risk', brief:
    'You judge downside. Shooting an idea costs the creator a full production cycle. For EACH idea: is it ' +
    'solo-shootable as described, does anything overpromise, and if the resulting reel underwhelms, does the ' +
    'suggestion look reckless in hindsight? score 5 = safe+feasible, 1 = reckless. Flag any performance-speak.' },
]

const capJudges = [
  { key: 'blind-rank-1', brief: '' }, { key: 'blind-rank-2', brief: '' },
]

const results = await parallel([
  ...(JSON.parse(IDEAS).length ? ideaJudges : []).map(j => () => agent(
    'Nine reel IDEAS were generated for three creator profiles by a tool that claims they are grounded in each ' +
    "creator's own reels (their reels are listed per item). YOUR LENS: " + j.brief +
    '\\n\\nIDEAS:\\n' + IDEAS + '\\n\\nReturn one judgment per idea (9 total).',
    { label: 'idea:' + j.key, phase: 'Judge', schema: IDEA_SCHEMA })),
  ...capJudges.map(j => () => agent(
    'For each reel below you get: what the reel is, the creator\\'s PAST captions (their real voice), and ' +
    'several candidate captions labeled A/B/C/D (order randomized; one of them is the caption the creator ' +
    'actually posted, the others are machine-written — you are NOT told which). For EACH reel: pick the BEST ' +
    'candidate (the one this creator should post), the WORST, and list every label that could PLAUSIBLY be ' +
    'the creator\\'s own writing judging by voice. Judge like a picky social media manager.' +
    '\\n\\nREELS:\\n' + CAPS + '\\n\\nReturn one ranking per reel (6 total).',
    { label: 'cap:' + j.key, phase: 'Judge', schema: CAP_SCHEMA })),
])

const nIdeaJudges = JSON.parse(IDEAS).length ? ideaJudges.length : 0
return {
  idea_judgments: results.slice(0, nIdeaJudges).filter(Boolean),
  caption_rankings: results.slice(nIdeaJudges).filter(Boolean),
}
'''

open("scripts/tmp/pt_judge_workflow.js", "w", encoding="utf-8", newline="\n").write(script)
print("emitted workflow with", len(ideas), "ideas and", len(blind_sets), "blind caption sets")
