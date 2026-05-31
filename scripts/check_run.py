"""Inspect an Apify run: status, cost, dataset size. python -m scripts.check_run <run_id>"""
import sys

from creative_director.apify.client import get_client


def main() -> None:
    run_id = sys.argv[1]
    c = get_client()
    run = c.run(run_id).get()
    print("status        :", run.get("status"))
    print("usageTotalUsd :", run.get("usageTotalUsd"))
    print("startedAt     :", run.get("startedAt"))
    print("finishedAt    :", run.get("finishedAt"))
    ds_id = run.get("defaultDatasetId")
    info = c.dataset(ds_id).get()
    print("dataset items :", info.get("itemCount"))


if __name__ == "__main__":
    main()
