"""Endpoint-level test for DELETE /me/account (Apple 5.1.1(v) account deletion).
Exercises the ROUTE: signup → seed an owned Upload + NoteFeedback → delete →
assert the user's rows are gone, the Bearer token no longer authenticates, and a
SECOND user's rows survive (deletion is owner-scoped, not a table wipe)."""
import os
import sys

sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("API_SESSION_SECRET", "t")

from fastapi.testclient import TestClient

from api.main import app
from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import NoteFeedback, Upload, User

init_db()
c = TestClient(app)

ok = True


def check(label, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' -- ' + str(extra)) if (extra and not cond) else ''}")


def user_id_for(email):
    with session_scope() as s:
        row = s.execute(
            User.__table__.select().where(User.email == email)
        ).first()
    return row[0] if row else None


def counts(uid):
    with session_scope() as s:
        u = s.query(User).filter(User.id == uid).count()
        up = s.query(Upload).filter(Upload.user_id == uid).count()
        nf = s.query(NoteFeedback).filter(NoteFeedback.user_id == uid).count()
    return u, up, nf


# --- The victim account: sign up, seed owned rows. ---
tok = c.post("/auth/email", json={"email": "del_victim@example.com"}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}
victim_id = user_id_for("del_victim@example.com")

# --- A bystander account whose rows must survive the deletion. ---
c.post("/auth/email", json={"email": "del_bystander@example.com"})
other_id = user_id_for("del_bystander@example.com")

with session_scope() as s:
    s.add(Upload(
        video_id="up_deltest_victim", user_id=victim_id, niche="ig_fitness",
        caption="mine", craft_read={"verdict": "x", "grounded": True},
    ))
    s.add(NoteFeedback(
        video_id="up_deltest_victim", user_id=victim_id,
        note="a dismissed note", reason="not_in_reel",
    ))
    s.add(Upload(
        video_id="up_deltest_other", user_id=other_id, niche="ig_food",
        caption="theirs", craft_read={"verdict": "y", "grounded": True},
    ))
    s.add(NoteFeedback(
        video_id="up_deltest_other", user_id=other_id,
        note="their note", reason="not_useful",
    ))

vu, vup, vnf = counts(victim_id)
check("seed: victim has user+upload+feedback rows", (vu, vup, vnf) == (1, 1, 1), (vu, vup, vnf))

# --- The authed call works before deletion. ---
r = c.get("/me/uploads", headers=H)
check("pre-delete: /me/uploads authenticates (200)", r.status_code == 200, r.status_code)

# --- Delete the account. ---
r = c.delete("/me/account", headers=H)
check("delete: 200", r.status_code == 200, r.text[:200])
check("delete: {ok: true}", r.json().get("ok") is True if r.status_code == 200 else False, r.text[:200])

# --- The victim's rows are gone. ---
vu, vup, vnf = counts(victim_id)
check("post-delete: victim User row gone", vu == 0, vu)
check("post-delete: victim Upload row gone", vup == 0, vup)
check("post-delete: victim NoteFeedback row gone", vnf == 0, vnf)

# --- The token no longer authenticates (deleted-user token dies). ---
r = c.get("/me/uploads", headers=H)
check("post-delete: stale token -> 401", r.status_code == 401, r.status_code)

# --- The bystander is untouched. ---
ou, oup, onf = counts(other_id)
check("bystander: rows survive (owner-scoped delete)", (ou, oup, onf) == (1, 1, 1), (ou, oup, onf))

# --- Cleanup the bystander's seeded rows so reruns stay clean. ---
with session_scope() as s:
    s.query(NoteFeedback).filter(NoteFeedback.video_id == "up_deltest_other").delete(
        synchronize_session=False
    )
    s.query(Upload).filter(Upload.video_id == "up_deltest_other").delete(
        synchronize_session=False
    )

print("\n" + ("ALL ACCOUNT DELETE TESTS PASSED" if ok else "SOME TESTS FAILED"))
sys.exit(0 if ok else 1)
