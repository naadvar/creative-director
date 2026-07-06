"""Seed a demo upload (LOCAL userdata.db) with a caption suggestion so the v1.2 UI
can be seen in the browser preview."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime

from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import Upload, User

init_db()
VID = "up_uidemo0000001"
with session_scope() as s:
    u = s.query(User).filter(User.email == "ui-demo@example.com").first()
    if u is None:
        u = User(created_at=datetime.utcnow(), email="ui-demo@example.com")
        s.add(u); s.flush()
    up = s.get(Upload, VID) or Upload(video_id=VID)
    up.user_id = u.id
    up.niche = "ig_fitness"
    up.title = "Leg day form check"
    up.caption = "NEW PR INCOMING!!! biggest lift of my life"
    up.duration_seconds = 22
    up.craft_read = {
        "grounded": True,
        "what_it_is": "A 22-second gym reel of three squat variations filmed side-on in a home gym.",
        "verdict": "Clean, well-lit demo with a confident side-on angle; the caption oversells a PR the reel never attempts.",
        "hook": "Opens mid-rep at the bottom of a squat.",
        "payoff": "Third variation lands at 0:16.",
        "pacing": "Steady, one cut per variation.",
        "biggest_opportunity": "0:02 - Your caption promises a PR attempt, but the reel is a form demo; the mismatch makes the strong teaching content feel like a bait-and-switch. Align the caption with what the reel actually shows.",
        "opportunity_dimension": "clarity",
        "lever_timestamp": "0:02",
        "blind_spots": ["0:09 - The middle variation's label holds under a second. Fix: hold each label 2s."],
        "done_well": ["Side-on angle shows depth clearly", "Consistent lighting across all three variations"],
        "on_screen_text_found": ["0:01 - SQUAT 3 WAYS"],
        "change_types": ["text_illegible"],
        "niche": "ig_fitness",
        "caption_suggestion": {
            "text": "3 squat variations, same bar, zero ego 🏋️ save this for leg day",
            "why": "matches their short punchy caption voice; describes what the reel actually shows",
        },
    }
    up.created_at = datetime.utcnow()
    s.add(up)
print("seeded", VID)
