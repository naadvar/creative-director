"""Tiny pod-side check: does SentenceTransformer load + encode on CPU?

Run on the pod after dep installs to confirm the description-embedding
backfill will work, without fighting PowerShell->ssh quote escaping.
"""
import os

os.environ["CUDA_VISIBLE_DEVICES"] = ""

try:
    from sentence_transformers import SentenceTransformer

    m = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
    v = m.encode(["hello world"])
    print("ST_OK shape=", v.shape)
except Exception as e:  # noqa: BLE001
    print("ST_FAILED:", type(e).__name__, str(e)[:300])
