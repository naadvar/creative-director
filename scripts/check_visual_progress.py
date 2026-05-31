"""Print Wave 2 backfill progress: populated count + log tail. No quoting pain."""
import sqlite3

c = sqlite3.connect("data/creative_director.db")
n = c.execute(
    "SELECT COUNT(1) FROM video_features WHERE hook_face_present_frac IS NOT NULL"
).fetchone()[0]
total = c.execute(
    "SELECT COUNT(1) FROM video_features vf JOIN videos v ON v.id=vf.video_id "
    "JOIN channels ch ON ch.id=v.channel_id WHERE ch.niche='ig_fitness'"
).fetchone()[0]
print(f"populated_visual: {n} / {total} ig_fitness")
try:
    with open("/workspace/v3_visual_backfill.log") as f:
        lines = f.readlines()
    print("--- log tail ---")
    print("".join(lines[-5:]))
except Exception as e:  # noqa: BLE001
    print("log read err:", e)
