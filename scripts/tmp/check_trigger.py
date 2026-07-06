import sys, json, sqlite3, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

con = sqlite3.connect("data/creative_director.db"); con.row_factory = sqlite3.Row
rows = con.execute("SELECT craft_read FROM video_features WHERE craft_read IS NOT NULL").fetchall()

post_caption = onscreen = ambiguous = 0
samples = {"post": [], "onscreen": []}
for r in rows:
    try:
        read = json.loads(r["craft_read"])
    except Exception:
        continue
    if not isinstance(read, dict) or read.get("grounded") is False:
        continue
    text = " ".join([str(read.get("biggest_opportunity") or "")] + [str(b) for b in (read.get("blind_spots") or [])])
    if not re.search(r"\bcaptions?\b", text, re.I):
        continue
    # classify: possessive/singular post-caption language vs subtitle language
    is_post = bool(re.search(r"\b(your|the|its|post)\s+caption\b|\bcaption (sets|promises|says|reads|mentions)\b", text, re.I))
    is_sub = bool(re.search(r"\bcaptions\b|\bsubtitle|\bcaption (?:text|overlay)s?\b", text, re.I))
    if is_post and not is_sub:
        post_caption += 1
        if len(samples["post"]) < 3: samples["post"].append(text[:130])
    elif is_sub and not is_post:
        onscreen += 1
        if len(samples["onscreen"]) < 3: samples["onscreen"].append(text[:130])
    else:
        ambiguous += 1

print(f"post-caption sense: {post_caption} | on-screen/subtitle sense: {onscreen} | both/ambiguous: {ambiguous}")
print("\npost samples:")
for s in samples["post"]: print("  -", s)
print("onscreen samples:")
for s in samples["onscreen"]: print("  -", s)
