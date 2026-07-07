"""Unit tests for caption-as-remedy: trigger, validators, retry->honest-absence."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("API_SESSION_SECRET", "t")

import creative_director.advice.captions as cap

ok = True
def check(label, cond, extra=""):
    global ok; ok = ok and bool(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' -- ' + str(extra)) if (extra and not cond) else ''}")

print("A. trigger (caption_implicated):")
check("lever mentions caption -> True",
      cap.caption_implicated({"biggest_opportunity": "0:02 - Your caption sets up a payoff the frames don't show."}))
check("blind spot mentions captions -> True",
      cap.caption_implicated({"biggest_opportunity": "x", "blind_spots": ["0:05 - the captions overlap"]}))
check("no caption mention -> False",
      not cap.caption_implicated({"biggest_opportunity": "0:07 - hold the text longer", "blind_spots": []}))
check("non-dict -> False", not cap.caption_implicated(None))

print("B. validators:")
check("clean caption passes", cap._valid({"caption": "leg day but make it honest 🦵"})[0])
check("tool leak rejected", not cap._valid({"caption": "New reel! (text size fixed for readability)"})[0])
check("craft-note leak rejected", not cap._valid({"caption": "Per the craft read, watch my hinge"})[0])
check("performance-speak rejected", not cap._valid({"caption": "this one's going viral fr"})[0])
check("empty rejected", not cap._valid({"caption": "  "})[0])
check("absurdly long rejected", not cap._valid({"caption": "x" * 1300})[0])
check("invented @handle rejected",
      not cap._valid({"caption": "styling with @some_random_brand today"}, "my past caption text")[0])
check("known @handle allowed",
      cap._valid({"caption": "back with @gisou again"}, "loved working with @Gisou last month")[0])

print("C. generation flow (mocked LLM):")
READ = {"what_it_is": "A gym demo of three squat variations.",
        "biggest_opportunity": "0:02 - Your caption promises a PR attempt the reel never shows.",
        "blind_spots": [], "on_screen_text_found": [], "grounded": True}
calls = {"n": 0}
def good_llm(system, user):
    calls["n"] += 1
    return {"caption": "three squat variations, zero ego 🏋️", "why": "matches their short-quip voice"}
cap._call = good_llm
out = cap.suggest_caption(READ, transcript="t", current_caption="PR DAY!!", past_captions=["quick one 💪", "form first"])
check("returns suggestion", out is not None and "squat" in out["text"], out)
check("one call when valid", calls["n"] == 1)

def leaky_then_good(system, user):
    calls["n"] += 1
    if calls["n"] == 2:
        return {"caption": "bumped the text size for readability, enjoy"}
    return {"caption": "three squat variations, zero ego"}
calls["n"] = 1  # so first call inside is n=2 (leaky), retry n=3 (good)
cap._call = leaky_then_good
out = cap.suggest_caption(READ, transcript="t", current_caption=None, past_captions=[])
check("retry after leak -> good caption", out is not None and "readability" not in out["text"], out)

def always_bad(system, user):
    return {"caption": "we're going viral with this one"}
cap._call = always_bad
out = cap.suggest_caption(READ, transcript="t", current_caption=None, past_captions=[])
check("two bad -> honest None", out is None)

def boom(system, user):
    raise RuntimeError("provider down")
cap._call = boom
out = cap.suggest_caption(READ, transcript=None, current_caption=None, past_captions=[])
check("provider failure -> None (no crash)", out is None)

print("D. trigger matrix (fine caption never rewritten; absent caption always offered):")
calls["n"] = 0
def counter(system, user):
    calls["n"] += 1
    return {"caption": "a solid grounded caption"}
cap._call = counter
NON_IMPLICATED = {"biggest_opportunity": "0:04 - tighten the hook", "blind_spots": [], "what_it_is": "a gym demo"}
# fine caption + non-implicating read -> nothing (zero LLM calls)
out = cap.suggest_caption(NON_IMPLICATED, transcript=None, current_caption="leg day, no ego", past_captions=[])
check("fine caption -> None, zero LLM calls", out is None and calls["n"] == 0)
# NO caption -> suggestion even though read never mentions captions
out = cap.suggest_caption(NON_IMPLICATED, transcript="t", current_caption=None, past_captions=["past cap"])
check("absent caption -> suggestion offered", out is not None and calls["n"] == 1, out)
# empty-string caption counts as absent
calls["n"] = 0
out = cap.suggest_caption(NON_IMPLICATED, transcript="t", current_caption="   ", past_captions=[])
check("whitespace caption counts as absent", out is not None and calls["n"] == 1)
# implicated + caption present still fires (the original case)
calls["n"] = 0
out = cap.suggest_caption(READ, transcript="t", current_caption="PR DAY!!", past_captions=[])
check("implicated caption still fires", out is not None and calls["n"] == 1)

print("\n" + ("ALL CAPTION TESTS PASSED" if ok else "SOME TESTS FAILED"))
sys.exit(0 if ok else 1)
