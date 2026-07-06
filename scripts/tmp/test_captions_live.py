"""Live product-code regression: run the REAL suggest_caption() on caption-implicated
corpus reels (the exact trigger condition it ships with), plus a naive baseline.
Dumps pt_artifacts.json (ideas empty) for the blind judge panel."""
import sys, os, json, sqlite3
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("API_SESSION_SECRET", "t")

import httpx
from creative_director.config import settings
from creative_director.advice.captions import caption_implicated, suggest_caption
from creative_director.advice.craft_xray import _loads_robust

con = sqlite3.connect("data/creative_director.db"); con.row_factory = sqlite3.Row
rows = con.execute(
    """SELECT v.id, v.description AS caption, v.channel_id, vf.transcript, vf.craft_read
       FROM videos v JOIN video_features vf ON vf.video_id = v.id
       JOIN channels c ON c.id = v.channel_id
       WHERE vf.transcript IS NOT NULL AND vf.transcript != '' AND vf.craft_read IS NOT NULL
         AND v.description IS NOT NULL AND length(v.description) > 30
         AND c.niche IN ('ig_fitness','ig_food','ig_travel','ig_fashion')
       LIMIT 3000""").fetchall()

# keep only reels whose READ implicates the caption — the product trigger
picked = []
for r in rows:
    try:
        read = json.loads(r["craft_read"])
    except Exception:
        continue
    if not isinstance(read, dict) or read.get("grounded") is False:
        continue
    if caption_implicated(read):
        picked.append((r, read))
print(f"caption-implicated corpus reels found: {len(picked)}")

# one per channel, up to 6
seen, chosen = set(), []
for r, read in picked:
    if r["channel_id"] in seen:
        continue
    seen.add(r["channel_id"]); chosen.append((r, read))
    if len(chosen) == 6:
        break

def naive(what):
    resp = httpx.post(settings.craft_read_base_url.rstrip("/") + "/chat/completions",
        json={"model": settings.craft_read_model, "max_tokens": 200, "temperature": 0.8,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": 'You write Instagram captions. Return ONLY JSON {"caption": "..."}.'},
                            {"role": "user", "content": f"Write an engaging Instagram caption for a reel about: {what[:120]}"}]},
        timeout=120, headers={"Authorization": f"Bearer {settings.craft_read_api_key}"})
    resp.raise_for_status()
    out = _loads_robust(resp.json()["choices"][0]["message"]["content"])
    return (out or {}).get("caption")

OUT = {"ideas": [], "captions": []}
for r, read in chosen:
    past = [row["description"][:220] for row in con.execute(
        "SELECT description FROM videos WHERE channel_id=? AND id!=? AND description IS NOT NULL AND length(description)>10 LIMIT 5",
        (r["channel_id"], r["id"])).fetchall()]
    sug = suggest_caption(read, transcript=r["transcript"], current_caption=r["caption"],
                          past_captions=past)
    if not sug:
        print(f"  {r['channel_id']}: SUPPRESSED (honest absence)")
        OUT["captions"].append({"video_id": r["id"], "niche_channel": r["channel_id"],
                                 "SUPPRESSED": True})
        continue
    OUT["captions"].append({
        "video_id": r["id"], "niche_channel": r["channel_id"],
        "what_it_is": (read.get("what_it_is") or "")[:200],
        "craft_note": (read.get("biggest_opportunity") or "")[:200],
        "real_caption_they_posted": r["caption"][:240],
        "their_past_captions": past,
        "our_options": [{"caption": sug["text"], "job": "their-dominant-style", "why": sug.get("why")}],
        "naive_baseline": naive(read.get("what_it_is") or "a reel"),
    })
    print(f"  {r['channel_id']}: generated")

json.dump(OUT, open("scripts/tmp/pt_artifacts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
done = sum(1 for c in OUT["captions"] if "our_options" in c)
print(f"\nDUMPED {done} caption sets ({len(OUT['captions']) - done} suppressed)")
