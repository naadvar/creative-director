"""Print current Apify billing-cycle spend. python -m scripts.apify_cost"""
import httpx

from creative_director.config import settings


def main() -> None:
    token = settings.apify_api_token
    if not token:
        print("APIFY_API_TOKEN not set")
        return
    r = httpx.get(
        f"https://api.apify.com/v2/users/me/usage/monthly?token={token}", timeout=30
    )
    r.raise_for_status()
    data = r.json()["data"]
    usage = data.get("monthlyServiceUsage", {})
    print(f"Cycle: {data.get('usageCycle', {}).get('startAt', '?')} -> "
          f"{data.get('usageCycle', {}).get('endAt', '?')}")
    print(f"Total this cycle: ${float(data.get('totalUsageCreditsUsdAfterVolumeDiscount') or data.get('totalUsageCreditsUsd') or 0):.2f}")
    for name, v in sorted(usage.items()):
        amt = v.get("baseAmountUsd") or v.get("amountUsd") or 0
        if amt:
            print(f"  {name:<28} ${float(amt):.2f}")


if __name__ == "__main__":
    main()
