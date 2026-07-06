"""Print the launch KPI report from the local userdata DB.

Usage:  python -m scripts.telemetry_report
Same aggregation as the live endpoint (GET /tools/kpis?key=... on the API host);
this offline version is for analyzing a downloaded copy of prod userdata.db
(set USERDATA_URL, e.g. sqlite:///./data/userdata_prod_copy.db).
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from creative_director.storage.kpis import compute_kpis, render_text  # noqa: E402

if __name__ == "__main__":
    print(render_text(compute_kpis()))
