"""Decode the judge panel: tabulate idea verdicts across lenses; unblind captions."""
import json, sys, html
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

p = r"C:/Users/naadv/AppData/Local/Temp/claude/C--Users-naadv/f9b00ced-2493-4376-8b2a-1ee4e493508d/tasks/w5y32qvk5.output"
o = json.load(open(p, encoding="utf-8"))
d = o.get("result", o); d = json.loads(d) if isinstance(d, str) else d
key = json.load(open("scripts/tmp/pt_caption_key.json", encoding="utf-8"))

# ---- ideas: cross-lens table ----
lenses = d["idea_judgments"]
print(f"=== IDEAS ({len(lenses)} lenses) ===")
# collate by concept
table = {}
for li, lens in enumerate(lenses):
    for j in lens["judgments"]:
        k = (j["profile"], j["concept"])
        table.setdefault(k, []).append((j["score"], j["verdict"]))
print(f"{'profile':<24} {'concept':<44} scores  verdicts")
for (prof, con), vals in table.items():
    scores = "/".join(str(v[0]) for v in vals)
    verds = ",".join(v[1] for v in vals)
    print(f"{prof:<24} {con[:43]:<44} {scores:<7} {verds}")

ship = sum(1 for vals in table.values() if sum(1 for v in vals if v[1] == "ship") >= 2)
kill = sum(1 for vals in table.values() if sum(1 for v in vals if v[1] == "kill") >= 2)
print(f"\nmajority-SHIP: {ship}/9 | majority-KILL: {kill}/9 | rest meh")

# ---- captions: unblind ----
print("\n=== CAPTIONS (blind, decoded) ===")
ranks = d["caption_rankings"]
stats = {"ours_best": 0, "real_best": 0, "base_best": 0, "ours_worst": 0, "base_worst": 0,
         "real_worst": 0, "ours_voice_pass": 0, "ours_total_votes": 0, "n": 0}
for lens_i, lens in enumerate(ranks):
    for r in lens["rankings"]:
        vid = r["video_id"]
        k = key.get(vid, {})
        if not k:
            continue
        stats["n"] += 1
        best = k.get(r["best"], "?")
        worst = k.get(r["worst"], "?")
        if best.startswith("ours"): stats["ours_best"] += 1
        elif best == "real_posted": stats["real_best"] += 1
        elif best == "baseline": stats["base_best"] += 1
        if worst.startswith("ours"): stats["ours_worst"] += 1
        elif worst == "baseline": stats["base_worst"] += 1
        elif worst == "real_posted": stats["real_worst"] += 1
        plaus = [k.get(x, "?") for x in (r.get("plausibly_the_creators") or [])]
        n_ours_options = sum(1 for v in k.values() if v.startswith("ours"))
        stats["ours_total_votes"] += n_ours_options
        stats["ours_voice_pass"] += sum(1 for x in plaus if x.startswith("ours"))
        print(f"  [{vid}] judge{lens_i+1}: best={best:<22} worst={worst:<12} "
              f"voice-plausible={[x for x in plaus]}")

n = stats["n"]
print(f"\nacross {n} judgments:")
print(f"  BEST:  ours {stats['ours_best']}/{n} | real {stats['real_best']}/{n} | baseline {stats['base_best']}/{n}")
print(f"  WORST: baseline {stats['base_worst']}/{n} | real {stats['real_worst']}/{n} | ours {stats['ours_worst']}/{n}")
print(f"  ours judged voice-plausible: {stats['ours_voice_pass']}/{stats['ours_total_votes']} option-votes")
