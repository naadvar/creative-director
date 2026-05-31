"""Thin wrapper over the Apify Python SDK.

Runs an actor synchronously and returns its default-dataset items. This is the
only piece of Apify-specific machinery the project needs; everything downstream
just maps ``list[dict]`` into Channel/Video/VelocitySnapshot rows.

Cost note: every ``run_actor`` call is billable. The IG pipeline batches all
profiles into one run per actor (one profile-scraper run + one reel-scraper
run for the whole seed list) to amortise cold-starts.

PERSONAL-V1 / TRAINING-CORPUS BOOTSTRAP only — see project memory for the
kill-criterion (do NOT use Apify-scraped data as the permanent product
foundation if commercialised).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from apify_client import ApifyClient
from loguru import logger

from creative_director.config import settings


@lru_cache(maxsize=1)
def get_client() -> ApifyClient:
    token = settings.apify_api_token
    if not token:
        raise RuntimeError(
            "APIFY_API_TOKEN not set. Add it to .env (Apify Console > "
            "Settings > Integrations > Personal API tokens)."
        )
    return ApifyClient(token)


def run_actor(
    actor_id: str,
    run_input: dict[str, Any],
    memory_mbytes: int = 1024,
    timeout_secs: int = 600,
    max_total_charge_usd: float | None = None,
) -> list[dict[str, Any]]:
    """Run an Apify actor synchronously and return its dataset items.

    Blocks until the actor finishes. Raises if the actor doesn't finish
    SUCCEEDED. The Free tier auto-deletes datasets after 7 days, so always
    materialise the items into local storage before returning to the caller.

    ``max_total_charge_usd`` is a hard server-side cost cap -- Apify halts
    the actor when its accumulated billed events exceed this. Use it on
    discovery / exploration runs to prevent another budget surprise.

    Pinned to apify-client>=2.5,<3 -- 3.0.0 has a pydantic-validation bug
    that rejects the actor-metadata shape Apify's API actually returns
    (e.g. PAY_PER_EVENT entries without ``pricePerUnitUsd``).
    """
    client = get_client()
    cap = f", cost_cap=${max_total_charge_usd}" if max_total_charge_usd else ""
    logger.info(f"apify: starting actor {actor_id} (memory={memory_mbytes}MB{cap})")
    run = client.actor(actor_id).call(
        run_input=run_input,
        memory_mbytes=memory_mbytes,
        timeout_secs=timeout_secs,
        max_total_charge_usd=max_total_charge_usd,
    )
    status = run.get("status")
    # TIMED-OUT (hit timeout_secs) and ABORTED (hit max_total_charge_usd) still
    # leave a usable partial dataset — take it rather than throwing away paid
    # work. Only a genuine FAILED/etc. is fatal.
    if status not in ("SUCCEEDED", "TIMED-OUT", "ABORTED"):
        raise RuntimeError(
            f"apify actor {actor_id} finished status={status} "
            f"(run id={run.get('id')})"
        )
    if status != "SUCCEEDED":
        logger.warning(
            f"apify actor {actor_id} ended {status} — using the partial dataset "
            f"(run id={run.get('id')})"
        )

    dataset_id = run["defaultDatasetId"]
    items = list(client.dataset(dataset_id).iterate_items())
    logger.info(f"apify: {actor_id} returned {len(items)} item(s)")
    return items
