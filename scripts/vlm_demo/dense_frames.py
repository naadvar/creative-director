"""Dense full-duration frame coverage for the 'VLM on the whole video' test.

For the reels whose 4-frame critique hallucinated TEMPORAL claims, sample 12
frames evenly across the ENTIRE clip and write 3 readable strips of 4 (early /
mid / late). Feeding all three to a vision agent approximates 'the VLM saw the
whole video' — the test is whether the temporal hallucinations then vanish.
"""
import os
import tempfile
from pathlib import Path

import cv2

from creative_director.config import settings
from creative_director.storage import media

OUT = Path("data/tmp/vlm_frames_dense")
OUT.mkdir(parents=True, exist_ok=True)

# (vid, the 4-frame critique's temporal error the skeptic caught)
REELS = [
    ("ig_DWBmcPjMNd3", "called 'frozen/static' but band exercise is in motion"),
    ("ig_DXVzPcXksuY", "fix said 'cut first ~1s' but the hand blocks lens at the END"),
    ("ig_DWBGNORjIQy", "'pancakes barely change frame 1-2' but frame 1 is actually black"),
]


def dense(vid):
    cl = media._client()
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        tmp = tf.name
    cl.download_file(settings.r2_bucket, media.video_key(vid), tmp)
    cap = cv2.VideoCapture(tmp)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    nframes = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    dur = (nframes / fps) if nframes else 12.0
    ts = [round(dur * i / 11.0, 2) for i in range(12)]  # 12 evenly across full clip
    frames = []
    for t in ts:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(min(t, dur - 0.05) * fps))
        ok, fr = cap.read()
        if ok:
            h = 360
            w = int(fr.shape[1] * h / fr.shape[0])
            fr = cv2.resize(fr, (w, h))
            # stamp the timestamp so the agent can anchor temporal claims
            cv2.putText(fr, f"{t:.1f}s", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
            cv2.putText(fr, f"{t:.1f}s", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            frames.append(fr)
    cap.release()
    os.unlink(tmp)
    paths = []
    for i, lbl in enumerate(("a", "b", "c")):
        chunk = frames[i * 4:(i + 1) * 4]
        if chunk:
            p = OUT / f"{vid}_{lbl}.jpg"
            cv2.imwrite(str(p), cv2.hconcat(chunk))
            paths.append(str(p))
    return dur, ts, paths


for vid, note in REELS:
    dur, ts, paths = dense(vid)
    print(f"{vid}: dur~{dur:.1f}s, 12 frames @ {ts}")
    for p in paths:
        print("   ", p)
