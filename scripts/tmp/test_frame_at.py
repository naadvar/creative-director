"""Endpoint-level test for GET /videos/{id}/frame-at — the craft-note "frame receipt".

Exercises the ROUTE against a REAL corpus mp4 (scripts/tmp/up_bc0709e901ea.mp4):
seeds an Upload row whose video_file_path points at that file (the same resolution
the /file endpoint uses for uploads), then asserts a real JPEG comes back, that an
out-of-range t clamps instead of failing, and that an unknown id 404s. Uses cv2 on
the host (already a dependency); no LLM, no network."""
import os
import sys

sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("API_SESSION_SECRET", "t")

from fastapi.testclient import TestClient

from api.main import app
from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import Upload

init_db()
c = TestClient(app)

MP4 = os.path.join("scripts", "tmp", "up_bc0709e901ea.mp4")
VID = "up_frametest1"

ok = True


def check(label, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' -- ' + str(extra)) if (extra and not cond) else ''}")


def seed():
    with session_scope() as s:
        s.add(Upload(
            video_id=VID, user_id=-777, niche="ig_fitness", caption="frame test",
            video_file_path=os.path.abspath(MP4),
            craft_read={"verdict": "x", "grounded": True},
        ))


def unseed():
    with session_scope() as s:
        s.query(Upload).filter(Upload.video_id == VID).delete(synchronize_session=False)


check("fixture mp4 present", os.path.exists(MP4), MP4)

unseed()
try:
    seed()

    # 1. A valid time -> 200 image/jpeg with a nonzero body (a real decoded frame).
    r = c.get(f"/videos/{VID}/frame-at", params={"t": 1})
    check("t=1: 200", r.status_code == 200, r.status_code)
    check("t=1: image/jpeg", r.headers.get("content-type") == "image/jpeg", r.headers.get("content-type"))
    check("t=1: nonzero body", len(r.content) > 0, len(r.content))
    check("t=1: cache header", "max-age=86400" in (r.headers.get("cache-control") or ""), r.headers.get("cache-control"))

    # 2. Out-of-range t clamps to the last frame instead of 404ing.
    r = c.get(f"/videos/{VID}/frame-at", params={"t": 9999})
    check("t=9999 clamps: 200", r.status_code == 200, r.status_code)
    check("t=9999 clamps: nonzero body", len(r.content) > 0, len(r.content))

    # 3. t=0 (first frame) works.
    r = c.get(f"/videos/{VID}/frame-at", params={"t": 0})
    check("t=0: 200", r.status_code == 200, r.status_code)

    # 4. Unknown video id -> 404 (no file to resolve).
    r = c.get("/videos/up_does_not_exist_zzz/frame-at", params={"t": 1})
    check("missing video: 404", r.status_code == 404, r.status_code)
finally:
    unseed()

print("\n" + ("ALL FRAME-AT TESTS PASSED" if ok else "SOME TESTS FAILED"))
sys.exit(0 if ok else 1)
