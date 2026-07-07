"""Live e2e: same-file memoization on prod. Upload a reel (full pipeline run),
then upload the SAME bytes again with the same niche+caption — the second must
come back instantly, already done, pointing at the FIRST video_id. Cleans up."""
import pathlib
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import httpx

B = "https://creative-director-api-production.up.railway.app"
mp4 = pathlib.Path("scripts/tmp/up_bc0709e901ea.mp4")
assert mp4.exists(), "test file missing"

c = httpx.Client(base_url=B, timeout=120)
tok = c.post("/auth/email", json={"email": "pipelinecheck@example.com"}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}


def upload():
    with mp4.open("rb") as fh:
        r = c.post("/upload", headers=H,
                   files={"file": ("dedupe_check.mp4", fh, "video/mp4")},
                   data={"niche": "ig_fitness", "caption": ""})
    r.raise_for_status()
    return r.json()


# --- first upload: full pipeline ---
j1 = upload()
print("upload 1:", j1["status"], "|", j1["message"])
vid1 = None
for i in range(90):
    st = c.get(f"/upload/{j1['job_id']}", headers=H).json()
    if st["status"] == "done":
        vid1 = st["video_id"]
        print(f"  done after ~{i*5}s -> {vid1}")
        break
    if st["status"] == "error":
        print("  JOB 1 ERROR:", st.get("error")); sys.exit(1)
    if i % 6 == 0:
        print(f"  [{i*5:>3}s] {st.get('message', '')}")
    time.sleep(5)
else:
    print("  TIMEOUT"); sys.exit(1)

read1 = c.get(f"/videos/{vid1}/craft-read").json()
grounded = (read1.get("read") or {}).get("grounded")
print("  grounded:", grounded)
if grounded is not True:
    print("  first read not grounded=True — dedupe can't be tested on it; cleaning up")
    c.delete(f"/me/uploads/{vid1}", headers=H)
    sys.exit(1)

# --- second upload, identical bytes + inputs: must dedupe instantly ---
t0 = time.time()
j2 = upload()
dt = time.time() - t0
print(f"\nupload 2 ({dt:.1f}s): status={j2['status']} video_id={j2['video_id']}")
print("  message:", j2["message"])

ok = True
if j2["status"] != "done":
    print("  FAIL: expected instant done"); ok = False
if j2["video_id"] != vid1:
    print(f"  FAIL: expected {vid1}, got {j2['video_id']}"); ok = False
if dt > 15:
    print("  FAIL: not instant"); ok = False

# the existing read must still serve
read2 = c.get(f"/videos/{vid1}/craft-read").json()
if not read2.get("available"):
    print("  FAIL: read no longer served"); ok = False

# --- cleanup, then confirm forgetting: row gone means no future match ---
d = c.delete(f"/me/uploads/{vid1}", headers=H)
print("\ncleanup delete:", d.status_code)

print("\n" + ("DEDUPE LIVE E2E PASSED" if ok else "DEDUPE LIVE E2E FAILED"))
sys.exit(0 if ok else 1)
