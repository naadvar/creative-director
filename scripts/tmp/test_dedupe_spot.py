"""Dedupe-promoted-spot tests — using the REAL texts from the tester's screenshots."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("API_SESSION_SECRET", "t")

from api.routers.videos import _dedupe_promoted_spot as dd

ok = True
def check(label, cond, extra=""):
    global ok; ok = ok and bool(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' -- ' + str(extra)) if (extra and not cond) else ''}")

# Screenshot variant A: lever promoted from the 0:02 overlay spot
A = {
    "biggest_opportunity": "At 0:02, reposition the deadlifts text overlay higher in the frame or reduce its font size slightly to ensure full legibility without cutting off the instruction — this preserves clarity during the critical workout setup phase.",
    "lever_timestamp": "0:02",
    "blind_spots": [
        "0:02 - The text overlay for the deadlifts is partially cut off at the bottom of the frame, making it hard to read the full instruction. Fix: Reposition the text higher in the frame or reduce font size slightly to ensure full legibility without obscuring the action.",
        "0:11 - The final exercise (burpees) is shown in a wide shot with background activity, which distracts from the main action. Fix: Tighten the frame to focus on the creator's form during the burpee.",
    ],
}
out = dd(A)
check("variant A: promoted 0:02 spot removed", len(out["blind_spots"]) == 1, out["blind_spots"])
check("variant A: unrelated 0:11 spot kept", "burpees" in out["blind_spots"][0])
check("original read not mutated", len(A["blind_spots"]) == 2)

# Screenshot variant B: different phrasing, same promotion
B = {
    "biggest_opportunity": "At 0:02, increase the font size of the text detailing the first exercise ('EVERY 3 MINUTES FOR 15 MINUTES...') so it's readable without forcing the viewer to pause or refocus — this ensures the workout structure is immediately clear and actionable.",
    "lever_timestamp": "0:02",
    "blind_spots": [
        "0:02 - The text detailing the first exercise ('EVERY 3 MINUTES FOR 15 MINUTES...') is small and could be missed if the viewer is focused on the movement. Fix: Increase the font size or add a brief pause on the text to ensure readability.",
        "0:11 - The final exercise segment begins with a wide shot of the gym, which momentarily distracts from the creator's action. Fix: Tighten the frame.",
    ],
}
out = dd(B)
check("variant B: promoted spot removed", len(out["blind_spots"]) == 1)
check("variant B: 0:11 kept", "wide shot" in out["blind_spots"][0])

# A lever at a timestamp with a DIFFERENT topic at the same second must survive
C = {
    "biggest_opportunity": "At 0:05, hold the opening shot a beat longer so the hook lands before the first cut.",
    "lever_timestamp": "0:05",
    "blind_spots": [
        "0:05 - The background music spikes loudly over the intro voiceover. Fix: duck the track under the voice.",
    ],
}
out = dd(C)
check("same-timestamp different-topic spot kept", len(out["blind_spots"]) == 1, out["blind_spots"])

# no lever / no spots -> untouched
check("no lever -> untouched", dd({"blind_spots": ["x"]})["blind_spots"] == ["x"])
check("no spots -> untouched", dd({"biggest_opportunity": "x"}) .get("blind_spots") is None)
check("non-dict passthrough", dd(None) is None)

print("\n" + ("ALL DEDUPE TESTS PASSED" if ok else "SOME TESTS FAILED"))
sys.exit(0 if ok else 1)
