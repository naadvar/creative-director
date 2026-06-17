"""Check RunPod serverless endpoint health: worker + job-queue state."""
import httpx

from creative_director.config import settings

root = (settings.vlm_base_url or "").rstrip("/").replace("/openai/v1", "")
h = {"Authorization": f"Bearer {settings.vlm_api_key or ''}"}
print("endpoint root:", root)
try:
    r = httpx.get(f"{root}/health", headers=h, timeout=30)
    print("health:", r.status_code, r.text)
except Exception as e:  # noqa: BLE001
    print("health FAILED:", type(e).__name__, str(e)[:300])
