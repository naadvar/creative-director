from googleapiclient.discovery import Resource, build

from creative_director.config import settings


def get_youtube_client() -> Resource:
    if not settings.youtube_api_key:
        raise RuntimeError(
            "YOUTUBE_API_KEY not set. Add it to .env (see .env.example)."
        )
    return build(
        "youtube",
        "v3",
        developerKey=settings.youtube_api_key,
        cache_discovery=False,
    )
