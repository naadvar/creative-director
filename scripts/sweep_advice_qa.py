"""QA sweep: pull the advice surfaces for a stratified edge-case sample and
dump a human-readable report to eyeball for absurd/unactionable advice.

Strata: voiceover-led talking (face<0.3), faceless demos (face<0.05),
borderline-face talking (0.3-0.45), ultra-short (<=7s), long (>=90s), and
normal controls — across niches.

    python -m scripts.sweep_advice_qa            # writes data/tmp/sweep_report.txt
"""
from __future__ import annotations

import sqlite3

import httpx

BASE = "http://127.0.0.1:8000"
OUT = "data/tmp/sweep_report.txt"

Q = """
SELECT t.video_id, c.niche, AVG(t.has_face) AS face, f.transcript_word_count AS words,
       v.duration_seconds AS dur
FROM video_timeline t
JOIN videos v ON v.id = t.video_id
JOIN channels c ON c.id = v.channel_id
JOIN video_features f ON f.video_id = v.id
WHERE c.niche IN ('ig_fitness','ig_food','ig_travel','ig_fashion')
GROUP BY t.video_id
"""


def pick(rows, cond, per_niche, label):
    out, seen = [], {}
    for r in rows:
        vid, niche, face, words, dur = r
        if not cond(face or 0, words or 0, dur or 0):
            continue
        if seen.get(niche, 0) >= per_niche:
            continue
        seen[niche] = seen.get(niche, 0) + 1
        out.append((vid, niche, face or 0, words or 0, dur or 0, label))
    return out


def main() -> None:
    con = sqlite3.connect("data/creative_director.db")
    rows = con.execute(Q).fetchall()
    rows.sort(key=lambda r: r[0])  # deterministic

    sample = []
    sample += pick(rows, lambda f, w, d: w > 30 and f < 0.3, 2, "VOICEOVER-LED talking")
    sample += pick(rows, lambda f, w, d: w <= 30 and f < 0.05, 2, "FACELESS demo")
    sample += pick(rows, lambda f, w, d: w > 30 and 0.3 <= f < 0.45, 1, "BORDERLINE-face talking")
    sample += pick(rows, lambda f, w, d: 0 < d <= 7, 1, "ULTRA-SHORT")
    sample += pick(rows, lambda f, w, d: d >= 90, 1, "LONG")
    sample += pick(rows, lambda f, w, d: w > 30 and f >= 0.6 and 15 <= d <= 60, 1, "CONTROL talking")
    sample += pick(rows, lambda f, w, d: w <= 30 and f >= 0.4 and 15 <= d <= 60, 1, "CONTROL demo")

    lines = [f"ADVICE QA SWEEP — {len(sample)} videos\n" + "=" * 70]
    with httpx.Client(timeout=180) as c:
        for vid, niche, face, words, dur, label in sample:
            lines.append(f"\n### [{label}] {vid}  niche={niche} face={face:.2f} words={words} dur={dur}s")
            try:
                s = c.get(f"{BASE}/videos/{vid}/summary").json()
                lines.append(f"READ: {s['read']}")
                for w in s.get("worth_trying", []):
                    lines.append(f"  - {w['text']}")
            except Exception as e:  # noqa: BLE001
                lines.append(f"  summary ERROR: {e}")
            try:
                cp = c.get(f"{BASE}/videos/{vid}/cutplan").json()
                ac = c.get(f"{BASE}/videos/{vid}/autocut").json()
                lines.append(
                    f"CUTPLAN: trim={cp.get('suggested_trim_start')} "
                    f"sugg={len(cp.get('suggestions') or [])} | AUTOCUT changed={ac.get('changed')} "
                    f"removed={[(r['start'], r['end']) for r in (ac.get('removed') or [])]}"
                )
            except Exception as e:  # noqa: BLE001
                lines.append(f"  cutplan ERROR: {e}")
            try:
                fr = c.get(f"{BASE}/videos/{vid}/frame").json()
                for fnd in fr.get("findings", [])[:3]:
                    lines.append(f"  * {fnd}")
            except Exception as e:  # noqa: BLE001
                lines.append(f"  frame ERROR: {e}")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {OUT} ({len(sample)} videos)")


if __name__ == "__main__":
    main()
