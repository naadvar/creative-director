"""Quick read-only IG count check against an arbitrary creative_director.db file."""
import sqlite3, sys
db = sys.argv[1] if len(sys.argv) > 1 else "creative_director_processed.db"
con = sqlite3.connect(db)
cur = con.cursor()

def q(sql):
    return cur.execute(sql).fetchone()[0]

print(f"DB: {db}")
print("ig_ videos total              :", q("SELECT COUNT(*) FROM videos WHERE id LIKE 'ig_%'"))
print("ig_ with features             :", q("SELECT COUNT(*) FROM video_features WHERE video_id LIKE 'ig_%'"))
print("ig_ with timelines (distinct) :", q("SELECT COUNT(DISTINCT video_id) FROM video_timeline WHERE video_id LIKE 'ig_%'"))
print("ig_ NULL title_embedding      :", q("SELECT COUNT(*) FROM video_features WHERE video_id LIKE 'ig_%' AND title_embedding IS NULL"))
print("--- whole-DB totals ---")
print("total videos        :", q("SELECT COUNT(*) FROM videos"))
print("total features      :", q("SELECT COUNT(*) FROM video_features"))
print("timelines (distinct):", q("SELECT COUNT(DISTINCT video_id) FROM video_timeline"))
print("yt features (non-ig):", q("SELECT COUNT(*) FROM video_features WHERE video_id NOT LIKE 'ig_%'"))
