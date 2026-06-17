"""Submit a tiny job via the native /run route and poll /status — surfaces the
worker's actual error (or proves it processes) without a 600s sync hang."""
import time

import httpx

from creative_director.config import settings

root = (settings.vlm_base_url or "").rstrip("/").replace("/openai/v1", "")
h = {"Authorization": f"Bearer {settings.vlm_api_key or ''}", "Content-Type": "application/json"}
print("root:", root)

# native vLLM-worker input shape (matches the console's example curl)
r = httpx.post(f"{root}/run", headers=h, json={"input": {"prompt": "Say OK", "sampling_params": {"max_tokens": 10}}}, timeout=30)
print("submit:", r.status_code, r.text[:300])
job = r.json().get("id")
if not job:
    raise SystemExit("no job id")

for i in range(24):  # ~4 min
    s = httpx.get(f"{root}/status/{job}", headers=h, timeout=30)
    j = s.json()
    st = j.get("status")
    print(f"[{i*10}s] status={st}")
    if st in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"):
        print("final:", str(j)[:800])
        break
    time.sleep(10)

hr = httpx.get(f"{root}/health", headers=h, timeout=30)
print("health:", hr.text)
