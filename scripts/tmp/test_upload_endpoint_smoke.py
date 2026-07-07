"""Endpoint-level smoke for POST /upload — exercises the ROUTE (imports, guards,
dedupe branch), which unit tests on _find_existing_read cannot. No LLM calls:
a garbage 'video' exercises the fresh path up to the 422 duration probe, and a
pre-seeded Upload row + matching bytes exercises the instant-done dedupe path."""
import hashlib
import io
import os
import sys

sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("API_SESSION_SECRET", "t")

from fastapi.testclient import TestClient

from api.main import app
from creative_director.advice.craft_xray import READ_ENGINE_VERSION
from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import Upload, User

init_db()
c = TestClient(app)

ok = True


def check(label, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' -- ' + str(extra)) if (extra and not cond) else ''}")


tok = c.post("/auth/email", json={"email": "smoke_dedupe@example.com"}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}
with session_scope() as s:
    me = s.execute(
        User.__table__.select().where(User.email == "smoke_dedupe@example.com")
    ).first()
my_id = me[0]

JUNK = b"not really a video at all " * 100
JUNK_HASH = hashlib.sha256(JUNK).hexdigest()


def post(data_extra=None, headers_extra=None):
    return c.post(
        "/upload",
        headers={**H, **(headers_extra or {})},
        files={"file": ("x.mp4", io.BytesIO(JUNK), "video/mp4")},
        data={"niche": "ig_fitness", "caption": "smoke cap", **(data_extra or {})},
    )


def seed_row():
    with session_scope() as s:
        s.add(Upload(
            video_id="up_smoketest1", user_id=my_id, niche="ig_fitness",
            caption="smoke cap", file_hash=JUNK_HASH,
            craft_read={
                "verdict": "x", "grounded": True,
                "engine_version": READ_ENGINE_VERSION, "engine_niche": "ig_fitness",
            },
        ))


def unseed():
    with session_scope() as s:
        s.query(Upload).filter(Upload.video_id == "up_smoketest1").delete(
            synchronize_session=False
        )


unseed()
try:
    # 1. FRESH path: route runs end to end past the dedupe block (no match) and
    # fails honestly at the duration probe — proves no import/name errors anywhere
    # in the request path (the bug class the adversarial review caught).
    r = post()
    check("fresh path: 422 at duration probe (no 500)", r.status_code == 422, r.text[:200])

    # 2. DEDUPE path: same bytes + same inputs + seeded grounded row -> instant done
    # pointing at the existing video_id.
    seed_row()
    r = post()
    check("dedupe: 200", r.status_code == 200, r.text[:200])
    j = r.json() if r.status_code == 200 else {}
    check("dedupe: instant done", j.get("status") == "done", j)
    check("dedupe: existing video_id", j.get("video_id") == "up_smoketest1", j)
    check("dedupe: job pollable", c.get(f"/upload/{j.get('job_id')}").status_code == 200)

    # 3. changed inputs miss the cache and hit the fresh path again
    r = post({"caption": "different cap"})
    check("different caption: fresh path (422)", r.status_code == 422, r.text[:200])
    r = post({"niche": "ig_food"})
    check("different niche: fresh path (422)", r.status_code == 422, r.text[:200])

    # 4. junk prior/idea ids do NOT skip memoization (validated before the gate)
    r = post({"prior_video_id": "x"})
    check("junk prior_video_id still dedupes", r.status_code == 200 and r.json().get("status") == "done", r.text[:200])
    r = post({"idea_id": "zzz"})
    check("junk idea_id still dedupes", r.status_code == 200 and r.json().get("status") == "done", r.text[:200])

    # 5. a REAL-shaped prior id skips dedupe (revision re-check must run fresh)
    r = post({"prior_video_id": "up_0000000000aa"})
    check("real prior link skips dedupe (fresh 422)", r.status_code == 422, r.text[:200])
finally:
    unseed()

print("\n" + ("ALL UPLOAD ENDPOINT SMOKE TESTS PASSED" if ok else "SOME TESTS FAILED"))
sys.exit(0 if ok else 1)
