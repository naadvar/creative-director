"""Unit tests for the Ideas engine: validator rules, gating, cache, daily cap —
mocked LLM (no network). Plus the niche digest against the real local corpus DB."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("API_SESSION_SECRET", "test-secret")
# Use a THROWAWAY userdata db so we don't pollute the real local one.
import tempfile
_fd, _udb = tempfile.mkstemp(suffix=".db"); os.close(_fd)
os.environ["USERDATA_URL"] = f"sqlite:///{_udb}"

from creative_director.config import settings
settings.userdata_url = f"sqlite:///{_udb}"

# Reload db module bindings against the temp userdata db.
import importlib
import creative_director.storage.db as dbm
importlib.reload(dbm)
dbm.init_db()

import creative_director.profile.ideas as ideas
importlib.reload(ideas)  # rebind session_scope to the reloaded db module
# NOTE: ideas imports session_scope from creative_director.storage.db at import time;
# after reload of dbm, re-import to bind the new engines.
ideas.session_scope = dbm.session_scope

from creative_director.storage.models import Upload, User
from datetime import datetime, timedelta

ok = True
def check(label, cond, extra=""):
    global ok; ok = ok and bool(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' -- ' + str(extra)) if (extra and not cond) else ''}")

# ---- seed a fake creator with 4 grounded reads ----
READS = [
    ("up_aaaaaaaaaaa1", "Mirror-cam leg day form check", "A gym selfie-video where a woman demos three squat variations in a mirror, with text labels per variation.", ["Clear per-exercise text labels", "Consistent mirror framing"], ["text_illegible"], "visual_led"),
    ("up_aaaaaaaaaaa2", "10-min full body finisher", "A fast-cut montage of a full-body dumbbell circuit in a home gym, one text overlay per move.", ["High-energy cut rhythm"], ["text_illegible", "pacing_slow"], "visual_led"),
    ("up_aaaaaaaaaaa3", "What I eat before lifting", "A talking-head kitchen clip where she explains her pre-workout meal while prepping it.", ["Natural delivery to camera"], ["payoff_backloaded"], "talking_head"),
    ("up_aaaaaaaaaaa4", "Deadlift setup mistakes", "A gym demo of three deadlift setup mistakes and their fixes, shot side-on with text callouts.", ["Side-on angle shows the hinge clearly"], ["text_illegible"], "visual_led"),
]

with dbm.session_scope() as s:
    u = User(created_at=datetime.utcnow(), email="ideas-test@example.com", display_name="ideas-test")
    s.add(u); s.flush(); UID = u.id
    for i, (vid, title, wit, dw, cts, fmt) in enumerate(READS):
        s.add(Upload(
            video_id=vid, user_id=UID, niche="ig_fitness", title=title,
            craft_read={
                "what_it_is": wit, "done_well": dw, "change_types": cts,
                "blind_spots": [f"0:0{i} - note"] * len(cts),
                "format_class": fmt, "opportunity_dimension": "text",
                "grounded": True, "verdict": "v", "biggest_opportunity": "bo",
            },
            created_at=datetime.utcnow() - timedelta(days=len(READS) - i),
        ))

print("A. creator DNA:")
dna = ideas._creator_dna(UID)
check("n reads", dna["n"] == 4, dna["n"])
check("recurring gap = text_illegible", dna["gap_key"] == "text_illegible", dna["gap_key"])
check("gap tier recurring", dna["gap_tier"] == "recurring")
check("ids set", "up_aaaaaaaaaaa1" in dna["ids"])

GOOD_IDEA = {
    "concept": "Squat depth myths, side-on",
    "premise": "A side-on demo debunking three squat depth myths, using your mirror-format labels at each depth.",
    "format": "visual_led",
    "grounded_in": [{"video_id": "up_aaaaaaaaaaa1", "why": "reuses your per-exercise label format"}],
    "strength_used": {"video_id": "up_aaaaaaaaaaa4", "strength": "side-on angle shows the hinge", "how": "same angle for depth"},
    "beat_sheet": [
        {"beat": "Hook", "time": "0:00-0:02", "direction": "Open mid-rep at the bottom of a squat"},
        {"beat": "Myth 1", "time": "0:02-0:08", "direction": "Label holds 2s, lower third, 80px"},
        {"beat": "Payoff", "time": "0:08-0:15", "direction": "Side-by-side depth comparison"},
    ],
    "gap_guardrail": {"gap": "text_illegible", "plan": "Each label sits lower-third, large type, holds two full seconds before any cut."},
    "shoot_notes": "One session, phone on tripod, side-on.",
}

print("B. validator:")
okv, r = ideas._validate(GOOD_IDEA, dna)
check("good idea passes", okv, r)
import copy
bad = copy.deepcopy(GOOD_IDEA); bad["grounded_in"] = [{"video_id": "up_ffffffffffff", "why": "x"}]
check("fabricated citation rejected", not ideas._validate(bad, dna)[0])
bad = copy.deepcopy(GOOD_IDEA); bad["premise"] = "This will go viral with trending audio."
check("trend-speak rejected", not ideas._validate(bad, dna)[0])
bad = copy.deepcopy(GOOD_IDEA); bad["premise"] = "About 37% of reels do this."
check("model-authored stat rejected", not ideas._validate(bad, dna)[0])
bad = copy.deepcopy(GOOD_IDEA); bad["beat_sheet"][1]["direction"] = "Label fills 80% of frame width at 100% opacity"
check("spatial % direction NOT rejected", ideas._validate(bad, dna)[0], ideas._validate(bad, dna)[1])
bad = copy.deepcopy(GOOD_IDEA); bad["premise"] = "A gym selfie-video where a woman demos three squat variations in a mirror, with text labels per variation."
check("remix of existing reel rejected", not ideas._validate(bad, dna)[0])
bad = copy.deepcopy(GOOD_IDEA); bad["gap_guardrail"]["gap"] = "pacing_slow"
check("wrong gap key rejected", not ideas._validate(bad, dna)[0])
# the gap/production as the reel's SUBJECT -> rejected (v1.2 judge-panel rule)
bad = copy.deepcopy(GOOD_IDEA); bad["premise"] = "A reel showing how I make my on-screen text more readable for viewers."
check("gap-as-subject rejected", not ideas._validate(bad, dna)[0])
bad = copy.deepcopy(GOOD_IDEA); bad["concept"] = "Behind the scenes of setting up my cue cards"
check("production-as-subject rejected", not ideas._validate(bad, dna)[0])
# but text specs in BEAT DIRECTIONS stay legal
bad = copy.deepcopy(GOOD_IDEA); bad["beat_sheet"][1]["direction"] = "Label text large, lower third, holds 2s for readability"
check("text specs in beat directions still allowed", ideas._validate(bad, dna)[0], ideas._validate(bad, dna)[1])
# regenerate too similar to a PRIOR idea -> rejected
check("near-duplicate of prior idea rejected",
      not ideas._validate(copy.deepcopy(GOOD_IDEA), dna, [GOOD_IDEA["premise"]])[0])
check("distinct idea passes with priors",
      ideas._validate(copy.deepcopy(GOOD_IDEA), dna, ["A kitchen tour of meal-prep containers."])[0])
bad = copy.deepcopy(GOOD_IDEA); bad["beat_sheet"] = bad["beat_sheet"][:2]
check("2-beat sheet rejected", not ideas._validate(bad, dna)[0])
bad = copy.deepcopy(GOOD_IDEA); bad["shoot_notes"] = "Reach overhead on the last rep."
check("'reach overhead' NOT rejected (fitness verb)", ideas._validate(bad, dna)[0], ideas._validate(bad, dna)[1])
bad = copy.deepcopy(GOOD_IDEA); bad["shoot_notes"] = "This maximizes your reach."
check("'your reach' (performance) rejected", not ideas._validate(bad, dna)[0])

print("C. niche digest (real corpus):")
d = ideas._niche_digest("ig_fitness", "visual_led")
check("digest computed", d is not None and d["n"] > 1000, d and d["n"])
if d:
    check("has top-3 change types with pcts", len(d["top"]) == 3, d["top"])
    check("has exemplars", len(d["exemplars"]) >= 5, len(d["exemplars"]))
    print(f"      digest: n={d['n']}, top={d['top']}")

print("D. gating + cache + cap (mocked LLM):")
calls = {"n": 0, "last_user": ""}
# Distinct premises per call — the validator now rejects regenerates that lightly
# rephrase a prior idea, so the mock must vary like the real model would.
PREMISES = [
    "A side-on demo debunking three squat depth myths with planned label placement.",
    "One continuous take walking through a full warm-up circuit, camera fixed at hip height.",
    "The gym at 5am: what setting up for a heavy session actually looks like, condensed.",
    "Three grip mistakes on deadlifts, each shown from the knuckles' point of view.",
    "Episode one of a weekly series rating gym equipment by how beginners misuse it.",
    "A silent reel: one lift, no music, only chalk and breathing sounds carry it.",
    "Before/after of the same set filmed lazy versus braced, cut back to back.",
    "A deep-dive on bar path: one lift traced with an on-screen line, start to lockout.",
]
def fake_llm(system, user):
    i = calls["n"]; calls["n"] += 1; calls["last_user"] = user
    out = copy.deepcopy(GOOD_IDEA)
    out["concept"] = f"Concept variant {i}"
    out["premise"] = PREMISES[i % len(PREMISES)]
    return out
ideas._call_llm = fake_llm
ideas._use_openai_orig = None
import creative_director.advice.craft_xray as cx
cx._use_openai = lambda: True

out1 = ideas.compute_idea(UID)
check("generates + ready", out1.get("ready") is True, out1.get("reason"))
check("stat line is server-stamped", "3 of your 4 reads" in (out1.get("gap_stat_line") or ""), out1.get("gap_stat_line"))
check("digest line present + real pct", bool(out1.get("digest_line")), out1.get("digest_line"))
check("citations resolve", len(out1.get("citations") or []) >= 1)
print(f"      gap_stat_line: {out1.get('gap_stat_line')}")
print(f"      digest_line:  {out1.get('digest_line')}")
n_after_first = calls["n"]
out2 = ideas.compute_idea(UID)
check("cache hit (no new LLM call)", calls["n"] == n_after_first and out2.get("idea_id") == out1.get("idea_id"))
out3 = ideas.compute_idea(UID, fresh=True)
check("fresh regenerates", calls["n"] > n_after_first and out3.get("idea_id") != out1.get("idea_id"))
check("regenerate prompt carries a mandatory angle", "MANDATORY CREATIVE ANGLE" in calls["last_user"])
check("regenerate prompt carries a primary anchor", "PRIMARY ANCHOR" in calls["last_user"])
check("regenerate prompt lists prior concepts", "ALREADY PROPOSED" in calls["last_user"])

# suppression BEFORE the cap is exhausted: garbage LLM -> honest empty state after retry
def bad_llm(system, user):
    calls["n"] += 1
    return {"concept": "x"}
ideas._call_llm = bad_llm
outs = ideas.compute_idea(UID, fresh=True)
check("invalid output -> honest empty state", outs.get("ready") is False and "grounded idea" in (outs.get("reason") or ""), outs)
ideas._call_llm = fake_llm  # restore

for _ in range(5):
    ideas.compute_idea(UID, fresh=True)
outc = ideas.compute_idea(UID, fresh=True)
check("daily cap kicks in", outc.get("capped") is True, outc)
# unknown user -> gated, no LLM call
before = calls["n"]
out0 = ideas.compute_idea(999999)
check("0 reads -> ready:false, no LLM call", out0.get("ready") is False and calls["n"] == before)

print("\n" + ("ALL IDEAS TESTS PASSED" if ok else "SOME TESTS FAILED"))
try:
    dbm.userdata_engine.dispose()
    os.unlink(_udb)
except OSError:
    pass
sys.exit(0 if ok else 1)
