"""Pod diagnostic: run after dep installs. No inline-quoting headaches.

    python3 scripts/pod_diag.py
"""
import glob

print("=== gate imports ===")
try:
    from creative_director.model.dataset import FEATURE_NAMES, INTRINSIC_FEATURES

    print(f"GATE_OK features={len(FEATURE_NAMES)} intrinsic={len(INTRINSIC_FEATURES)}")
except Exception as e:  # noqa: BLE001
    print(f"GATE_FAIL {type(e).__name__}: {str(e)[:250]}")

print("=== model libs ===")
for lib in ("lightgbm", "xgboost", "catboost", "shap", "scipy", "sklearn"):
    try:
        m = __import__(lib)
        print(f"  {lib}: OK {getattr(m, '__version__', '?')}")
    except Exception as e:  # noqa: BLE001
        print(f"  {lib}: FAIL {type(e).__name__}")

print("=== mp4 archive on /workspace ===")
mp4s = glob.glob("/workspace/creative-director/data/videos/*.mp4")
ig_mp4s = glob.glob("/workspace/creative-director/data/videos/ig_*.mp4")
print(f"  total mp4={len(mp4s)}  ig_mp4={len(ig_mp4s)}")

print("=== numpy / torch / gpu ===")
import numpy

print(f"  numpy {numpy.__version__}")
try:
    import torch

    print(f"  torch {torch.__version__}  cuda_available={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  gpu={torch.cuda.get_device_name(0)}")
except Exception as e:  # noqa: BLE001
    print(f"  torch FAIL {type(e).__name__}: {str(e)[:200]}")

print("=== sentence-transformers ===")
try:
    import sentence_transformers

    print(f"  sentence_transformers {sentence_transformers.__version__}")
    import transformers

    print(f"  transformers {transformers.__version__}")
except Exception as e:  # noqa: BLE001
    print(f"  ST/transformers FAIL {type(e).__name__}: {str(e)[:200]}")
