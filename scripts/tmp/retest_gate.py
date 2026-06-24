"""Re-validate the gate after the channel-weighting fixes (thumb_text + music + gender +
invented-OST). Real fabrications must stay/become suppressed; the re-QA's confirmed
false-positives must flip to kept. Prints a PASS/FAIL table."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from creative_director.advice.craft_xray import ground_and_gate
from creative_director.storage.db import session_scope
from creative_director.storage.models import Video, VideoFeatures

# expected: True = should stay GROUNDED (keep), False = should be SUPPRESSED
CASES = [
    # original known fabrications + good (regression)
    ("ig_7EMg2kOhNE", False, "FAB hip-thrust+spotter"),
    ("ig_CYwehNiqyiD", False, "FAB shark"),
    ("ig_C8Vpxb-u-iY", False, "FAB vacuum/typing"),
    ("ig_DU8mPTngrt7", True,  "GOOD muscle-up"),
    ("ig_DYlYnWwz7uC", True,  "GOOD meal-prep"),
    ("ig_DWT8p1JjtL9", False, "FAB kettlebell (transcript=mobility)"),
    ("ig_DVO0goaj1pr", False, "FAB Oprah (caption=Adele)"),
    ("ig_DVyriTMDTW4", True,  "prev-FP leg/Alzheimer"),
    ("ig_DVtouodj492", True,  "prev-FP podcast/bodybuilders"),
    ("ig_DVbq3g-D8t3", True,  "prev-FP gym-anxiety"),
    ("ig_DU9LBkgkvkL", True,  "prev-FP cable-abduction"),
    ("ig_DS0mnVAj5Li", True,  "prev-FP birthday"),
    # re-QA confirmed FALSE POSITIVES — must now flip to KEEP
    ("ig_BKMmZM1Bvs7", True,  "FP gender (caption 230lb lift)"),
    ("ig_DC92OuEtL1i", True,  "FP music+thumb LOWER BODY MOBILITY"),
    ("ig_DTsHqaHD6bB", True,  "FP gender (caption Sumo Deads 140kg)"),
    ("ig_DVIhFHKjTl8", True,  "FP music (caption 4 esercizi)"),
    ("ig_DWJnuEJkUo5", True,  "FP caption 3x10 + thumb glute"),
    ("ig_DX9ji1vKjSd", True,  "FP thumb karipearce / off-topic caption"),
    ("ig_DXcb3KQDA-K", True,  "FP thumb carries OST"),
    # re-QA confirmed MAJOR fabrications (invented on-screen text) — must now SUPPRESS
    ("ig_C85JNsuSRQQ", False, "FAB invented 'Refuse to be defined' text build"),
    ("ig_DR8S6SIDQE1", False, "FAB invented '3 MESES' before/after"),
]

rows, passes, total = [], 0, 0
for vid, expect_grounded, tag in CASES:
    with session_scope() as s:
        v = s.get(Video, vid)
        f = s.query(VideoFeatures).filter(VideoFeatures.video_id == vid).first()
        if not f or not f.craft_read:
            rows.append((vid, "NO-READ", tag, "?"))
            continue
        read = dict(f.craft_read)
        read.pop("grounded", None)
        read.pop("grounding_reason", None)
        vp, tr, thumb = f.vlm_perception, f.transcript, f.thumb_text
        cap = v.title if v else None
    total += 1
    g = ground_and_gate(read, vp, tr, cap, thumb)
    got = g.get("grounded") is not False
    ok = (got == expect_grounded)
    passes += ok
    verdict = "kept" if got else "SUPPRESSED"
    reason = "" if got else " :: " + (g.get("grounding_reason") or "")[:80]
    rows.append((vid, "PASS" if ok else "FAIL", tag,
                 f"{verdict} (want {'keep' if expect_grounded else 'suppress'}){reason}"))

print(f"{'vid':<16} {'res':<5} {'case':<40} note")
print("-" * 120)
for vid, res, tag, note in rows:
    print(f"{vid:<16} {res:<5} {tag:<40} {note}")
print("-" * 120)
print(f"{passes}/{total} correct")
