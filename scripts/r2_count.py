"""Count objects in the R2 bucket under a prefix. python -m scripts.r2_count [prefix]"""
import sys

from creative_director.config import settings
from creative_director.storage import media


def main() -> None:
    prefix = sys.argv[1] if len(sys.argv) > 1 else ""
    c = media._client()
    paginator = c.get_paginator("list_objects_v2")
    n = 0
    size = 0
    for page in paginator.paginate(Bucket=settings.r2_bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            n += 1
            size += obj["Size"]
    label = prefix or "(all)"
    print(f"{label}: {n} objects, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
