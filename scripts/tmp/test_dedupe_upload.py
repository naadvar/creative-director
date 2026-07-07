"""Same-file memoization tests — _find_existing_read against the LOCAL userdata DB.

Inserts Upload rows for an impossible user id (negative), exercises every
match/no-match rule, then removes them. Also verifies the file_hash runtime
column migration applies on init_db()."""
import os
import sys

sys.path.insert(0, os.getcwd())  # run as `python scripts/tmp/...` from the repo root
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("API_SESSION_SECRET", "t")

from creative_director.advice.craft_xray import READ_ENGINE_VERSION
from creative_director.storage.db import init_db, session_scope, userdata_engine
from creative_director.storage.models import Upload

from api.routers.upload import _find_existing_read

init_db()  # applies the file_hash ALTER TABLE on an existing userdata.db
cols = {r[1] for r in userdata_engine.raw_connection().execute("PRAGMA table_info(uploads)")}
assert "file_hash" in cols, f"migration missing file_hash: {cols}"

UID = -999  # impossible real user id — safe to insert/delete
H = "a" * 64
OTHER_H = "b" * 64

ok = True


def check(label, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' -- ' + str(extra)) if (extra and not cond) else ''}")


def grounded_read(version=READ_ENGINE_VERSION, grounded=True, engine_niche="ig_fitness"):
    r = {"verdict": "x", "blind_spots": [], "grounded": grounded, "engine_niche": engine_niche}
    if version is not None:
        r["engine_version"] = version
    return r


def put(vid, *, niche="ig_fitness", caption="cap", read=None, fh=H, uid=UID, days_ago=0):
    from datetime import datetime, timedelta

    with session_scope() as s:
        s.add(Upload(
            video_id=vid, user_id=uid, niche=niche, caption=caption,
            craft_read=read, file_hash=fh,
            created_at=datetime.utcnow() - timedelta(days=days_ago),
        ))


def cleanup():
    with session_scope() as s:
        s.query(Upload).filter(Upload.video_id.like("up_ddtest%")).delete(
            synchronize_session=False
        )


cleanup()
try:
    # 1. exact match hits
    put("up_ddtest1", read=grounded_read())
    check("exact match -> hit", _find_existing_read(UID, H, "ig_fitness", "cap") == "up_ddtest1")

    # 2. input sensitivity — any changed input must miss
    check("different caption -> miss", _find_existing_read(UID, H, "ig_fitness", "other cap") is None)
    check("different niche -> miss", _find_existing_read(UID, H, "ig_food", "cap") is None)
    check("different hash -> miss", _find_existing_read(UID, OTHER_H, "ig_fitness", "cap") is None)
    check("different user -> miss", _find_existing_read(-998, H, "ig_fitness", "cap") is None)

    # 3. caption whitespace normalization (stored trailing space == same input)
    put("up_ddtest2", caption="cap2 ", read=grounded_read(), fh=OTHER_H)
    check("stored caption strips for compare", _find_existing_read(UID, OTHER_H, "ig_fitness", "cap2") == "up_ddtest2")

    cleanup()

    # 4. only SUCCESS memoizes — suppressed / ungated / no-read rows never match
    put("up_ddtest3", read=grounded_read(grounded=False))
    check("suppressed read -> miss", _find_existing_read(UID, H, "ig_fitness", "cap") is None)
    cleanup()
    put("up_ddtest4", read=grounded_read(grounded=None))
    check("ungated read -> miss", _find_existing_read(UID, H, "ig_fitness", "cap") is None)
    cleanup()
    put("up_ddtest5", read=None)
    check("no read -> miss", _find_existing_read(UID, H, "ig_fitness", "cap") is None)
    cleanup()

    # 5. engine upgrades retire cached reads
    put("up_ddtest6", read=grounded_read(version=READ_ENGINE_VERSION - 1))
    check("stale engine_version -> miss", _find_existing_read(UID, H, "ig_fitness", "cap") is None)
    cleanup()
    put("up_ddtest7", read=grounded_read(version=None))
    check("legacy read (no version) -> miss", _find_existing_read(UID, H, "ig_fitness", "cap") is None)
    cleanup()

    # 6. newest matching row wins; a bad newest doesn't shadow an older good one
    put("up_ddtest8", read=grounded_read(), days_ago=2)
    put("up_ddtest9", read=grounded_read(), days_ago=1)
    check("newest match wins", _find_existing_read(UID, H, "ig_fitness", "cap") == "up_ddtest9")
    put("up_ddtest10", read=grounded_read(grounded=False), days_ago=0)
    check("suppressed newest falls through to older grounded",
          _find_existing_read(UID, H, "ig_fitness", "cap") == "up_ddtest9")
    cleanup()

    # 7. deletion is forgetting — no row, no match
    check("after delete -> miss", _find_existing_read(UID, H, "ig_fitness", "cap") is None)

    # 8. niche-switch poisoning: the mismatch-chip PATCH rewrites Upload.niche in
    # place, but the read was GENERATED under the old niche — it must not match the
    # new niche, and must still match its true generation niche.
    put("up_ddtest11", niche="ig_fitness", read=grounded_read(engine_niche="ig_food"))
    check("switched row: new niche -> miss (read generated under old niche)",
          _find_existing_read(UID, H, "ig_fitness", "cap") is None)
    check("switched row: generation niche still hits",
          _find_existing_read(UID, H, "ig_food", "cap") == "up_ddtest11")
    cleanup()
finally:
    cleanup()

print("\n" + ("ALL DEDUPE-UPLOAD TESTS PASSED" if ok else "SOME TESTS FAILED"))
sys.exit(0 if ok else 1)
