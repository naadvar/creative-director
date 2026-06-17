"""Quick check: did the overnight rich backfill land in R2, and how complete is it?"""
import io
import json
from creative_director.config import settings
from creative_director.storage import media

KEY = "backfill/vlm_perception_rich.jsonl"
c = media._client()
try:
    h = c.head_object(Bucket=settings.r2_bucket, Key=KEY)
    print(f"R2 OBJECT FOUND: {KEY}")
    print(f"  size: {h['ContentLength']/1e6:.1f} MB")
    print(f"  last_modified: {h['LastModified']}")
except Exception as e:  # noqa: BLE001
    print(f"R2 OBJECT NOT FOUND ({KEY}): {str(e)[:120]}")
    raise SystemExit(0)

# download + tally
buf = io.BytesIO()
c.download_fileobj(settings.r2_bucket, KEY, buf)
lines = buf.getvalue().decode("utf-8", "replace").splitlines()
n = ok = skip = err = 0
for ln in lines:
    if not ln.strip():
        continue
    n += 1
    r = json.loads(ln)
    if r.get("vlm_perception"):
        ok += 1
    elif r.get("skip"):
        skip += 1
    else:
        err += 1
print(f"  records: {n}  ok(tagged)={ok}  skip(no_mp4)={skip}  err={err}")
print(f"  completion: {n}/14929 = {100*n/14929:.1f}% of corpus")
# show one good sample
for ln in lines:
    r = json.loads(ln)
    p = r.get("vlm_perception")
    if p and p.get("observed"):
        print("  sample:", json.dumps({k: p.get(k) for k in ("genre", "has_presenter", "opening_shot", "observed")}, ensure_ascii=False)[:400])
        break
