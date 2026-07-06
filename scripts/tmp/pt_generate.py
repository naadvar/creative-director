"""Pressure-test artifact generation for the v1.2 candidates.

A) Ideas from your DNA: 3 realistic creator profiles seeded from REAL corpus reads
   -> 3 ideas each (initial + 2 regenerates) via the actual engine.
B) Caption-as-remedy prototype: 6 real corpus reels (transcript + caption + read)
   -> 2 grounded caption options each (voice-matched from the channel's own past
   captions) + 1 deliberately-naive baseline (title-only, simulating a generic tool).

Dumps scripts/tmp/pt_artifacts.json for the adversarial judge panel.
"""
import sys, os, json, sqlite3, tempfile, random
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("API_SESSION_SECRET", "t")
_fd, _udb = tempfile.mkstemp(suffix=".db"); os.close(_fd)
from creative_director.config import settings
settings.userdata_url = f"sqlite:///{_udb}"

import importlib
import creative_director.storage.db as dbm
importlib.reload(dbm)
dbm.init_db()
import creative_director.profile.ideas as ideas
ideas.session_scope = dbm.session_scope

import httpx
from creative_director.advice.craft_xray import _loads_robust
from creative_director.storage.models import Upload, User
from datetime import datetime, timedelta

con = sqlite3.connect("data/creative_director.db"); con.row_factory = sqlite3.Row
OUT = {"ideas": [], "captions": []}

# ---------- A) IDEAS ----------
def pick_reads(niche, fmt, n=5):
    rows = con.execute(
        """SELECT vf.craft_read AS cr FROM video_features vf
           JOIN videos v ON v.id = vf.video_id
           JOIN channels c ON c.id = v.channel_id
           WHERE c.niche=? AND vf.craft_read IS NOT NULL LIMIT 900""", (niche,)).fetchall()
    out = []
    for r in rows:
        try: cr = json.loads(r["cr"])
        except Exception: continue
        if not isinstance(cr, dict) or cr.get("grounded") is False: continue
        if cr.get("format_class") != fmt or not cr.get("what_it_is"): continue
        out.append(cr)
        if len(out) == n: break
    return out

PROFILES = [
    ("fitness / visual_led", "ig_fitness", "visual_led", "fitA"),
    ("food / talking_head", "ig_food", "talking_head", "fooA"),
    ("travel / visual_led", "ig_travel", "visual_led", "trvA"),
]
uid_counter = 100
for label, niche, fmt, tag in PROFILES:
    picked = pick_reads(niche, fmt)
    if len(picked) < 4:
        print(f"skip {label}: {len(picked)} reads"); continue
    with dbm.session_scope() as s:
        u = User(created_at=datetime.utcnow(), email=f"pt-{tag}@example.com")
        s.add(u); s.flush(); uid = u.id
        for i, cr in enumerate(picked):
            s.add(Upload(video_id=f"up_{'%012x' % (uid_counter*1000+i)}"[:15], user_id=uid,
                         niche=niche, title=(cr.get("what_it_is") or "reel")[:60],
                         craft_read=cr, created_at=datetime.utcnow() - timedelta(days=len(picked)-i)))
    uid_counter += 1
    dna = ideas._creator_dna(uid)
    profile_summary = [r["what_it_is"][:110] for r in dna["reads"]]
    for k in range(3):
        o = ideas.compute_idea(uid, fresh=(k > 0))
        if o.get("ready"):
            OUT["ideas"].append({
                "profile": label, "their_reels": profile_summary,
                "gap": dna["gap_key"], "idea": o["idea"],
                "gap_stat_line": o.get("gap_stat_line"), "digest_line": o.get("digest_line"),
            })
        else:
            OUT["ideas"].append({"profile": label, "SUPPRESSED": o.get("reason")})
    print(f"ideas: {label} done")

# ---------- B) CAPTIONS ----------
def llm(system, user, max_tokens=500, temperature=0.8):
    r = httpx.post(
        settings.craft_read_base_url.rstrip("/") + "/chat/completions",
        json={"model": settings.craft_read_model, "max_tokens": max_tokens,
              "temperature": temperature, "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]},
        timeout=120, headers={"Authorization": f"Bearer {settings.craft_read_api_key}"})
    r.raise_for_status()
    return _loads_robust(r.json()["choices"][0]["message"]["content"])

CAPTION_SYSTEM = (
    "You are the same craft critic who just read this creator's reel; as part of the read you "
    "suggest the caption they should post with it. Ground ONLY in what is given: the transcript, "
    "the on-screen text, what the reel is, the craft note, and the creator's own PAST captions "
    "(learn their voice from these: emoji habits, length, tone, hashtag habits). RULES: "
    "(1) match their voice — if their captions are short and dry, yours are too; "
    "(2) if the reel withholds a reveal or payoff, the caption must NOT spoil it; "
    "(3) never performance language (viral, algorithm, engagement, followers, reach); "
    "(4) the first 100 characters must stand alone (that is what shows before '...more'); "
    "(5) no hashtags unless their past captions use them. "
    'Return ONLY JSON: {"options": [{"caption": "...", "job": "context-setter", "why": "one line"}, '
    '{"caption": "...", "job": "hook-question", "why": "one line"}]}'
)

rows = con.execute(
    """SELECT v.id, v.title, v.description AS caption, v.channel_id, vf.transcript, vf.craft_read
       FROM videos v JOIN video_features vf ON vf.video_id = v.id
       JOIN channels c ON c.id = v.channel_id
       WHERE vf.transcript IS NOT NULL AND vf.transcript != '' AND vf.craft_read IS NOT NULL
         AND v.description IS NOT NULL AND length(v.description) > 30
         AND c.niche IN ('ig_fitness','ig_food','ig_travel')
       ORDER BY c.niche, v.id LIMIT 400""").fetchall()
by_niche = {}
for r in rows:
    read = json.loads(r["craft_read"]) if r["craft_read"] else {}
    if not isinstance(read, dict) or read.get("grounded") is False: continue
    by_niche.setdefault(r["channel_id"].split("_")[0] + r["id"][:5], None)
    by_niche_key = r["channel_id"]
    by_niche.setdefault(by_niche_key, []) if isinstance(by_niche.get(by_niche_key), list) else None

# simpler: group manually
groups = {}
for r in rows:
    read = json.loads(r["craft_read"]) if r["craft_read"] else {}
    if not isinstance(read, dict) or read.get("grounded") is False: continue
    groups.setdefault(r["channel_id"], []).append((r, read))
candidates = [(ch, items) for ch, items in groups.items() if len(items) >= 3][:6]

random.seed(7)
for ch, items in candidates:
    (r, read) = items[0]
    past = [it[0]["caption"][:180] for it in items[1:4]]
    user_content = (
        f"WHAT THE REEL IS: {read.get('what_it_is','')[:220]}\n"
        f"CRAFT NOTE FROM THE READ: {read.get('biggest_opportunity','')[:220]}\n"
        f"ON-SCREEN TEXT: {json.dumps((read.get('on_screen_text_found') or [])[:6])}\n"
        f"TRANSCRIPT (excerpt): {r['transcript'][:600]}\n"
        f"THE CREATOR'S PAST CAPTIONS (voice reference):\n- " + "\n- ".join(past) +
        "\n\nWrite the two caption options. JSON only."
    )
    try:
        ours = llm(CAPTION_SYSTEM, user_content)
    except Exception as e:
        print("caption gen failed:", type(e).__name__); continue
    # naive baseline: what a generic tool sees (no frames, no transcript, no voice)
    try:
        base = llm(
            "You write Instagram captions. Return ONLY JSON {\"caption\": \"...\"}.",
            f"Write an engaging Instagram caption for a reel about: {read.get('what_it_is','a reel')[:120]}",
            max_tokens=200)
    except Exception:
        base = {"caption": "(baseline failed)"}
    OUT["captions"].append({
        "video_id": r["id"], "niche_channel": ch,
        "what_it_is": read.get("what_it_is", "")[:200],
        "craft_note": read.get("biggest_opportunity", "")[:200],
        "real_caption_they_posted": r["caption"][:240],
        "their_past_captions": past,
        "our_options": ours.get("options") if isinstance(ours, dict) else ours,
        "naive_baseline": base.get("caption"),
    })
    print(f"captions: {ch} done")

json.dump(OUT, open("scripts/tmp/pt_artifacts.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
n_ideas = sum(1 for i in OUT["ideas"] if "idea" in i)
print(f"\nDUMPED: {n_ideas} ideas ({sum(1 for i in OUT['ideas'] if 'SUPPRESSED' in i)} suppressed), "
      f"{len(OUT['captions'])} caption sets -> scripts/tmp/pt_artifacts.json")

try:
    dbm.userdata_engine.dispose(); os.unlink(_udb)
except OSError:
    pass
