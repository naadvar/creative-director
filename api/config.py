"""API-layer settings.

Kept separate from the pipeline's ``creative_director.config``: it reads the
same ``.env`` file but only ``API_``-prefixed keys, so server tuning never
collides with pipeline settings.
"""
from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="API_",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8000

    # Origins allowed to call the API from a browser — the React dev servers
    # (Vite on 5173, Next on 3000) plus their 127.0.0.1 aliases, and the native
    # Capacitor app webviews (iOS: capacitor://localhost, Android: http://localhost).
    # The Vercel web app calls the API through its same-origin /api proxy, so it
    # needs no CORS entry.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "capacitor://localhost",
        "http://localhost",
        "ionic://localhost",
    ]

    # The corpus the advice layer is built for. Only fitness is featurized;
    # label_scheme is the age-banded views/subs scheme the model gate uses.
    niche: str = "fitness"
    label_scheme: str = "views_per_sub_aged_v1"

    # Demo curation: when True, the public browse/niches only surface reels that
    # have a Qwen craft read (VideoFeatures.craft_read), so every browsable reel
    # has the hero card. Reversible (set API_CORPUS_REQUIRE_CRAFT_READ=false) —
    # the rows stay in the DB so benchmarks keep full strength.
    corpus_require_craft_read: bool = True

    # --- Auth / session ---------------------------------------------------
    # Signed-cookie session secret. MUST be overridden in production
    # (API_SESSION_SECRET in .env). The dev default is intentionally obvious.
    session_secret: str = "dev-insecure-session-secret-change-me"
    # Private tester tools (/tools/*). Unset = the routes 404. Set API_TOOLS_KEY
    # to any secret string; share links as /tools/reel-grab?key=<that string>.
    tools_key: Optional[str] = None
    # Where to send the browser after auth completes (the SPA).
    frontend_base_url: str = "http://localhost:5173"
    # Dev-only: enables /auth/dev-login, which signs in a demo creator (no
    # OAuth) whose "Your Reels" is populated from the existing corpus so you
    # can preview the authed app. MUST be False in production.
    allow_dev_login: bool = True

    # --- Instagram Login / Meta Graph OAuth -------------------------------
    # Create a Meta app (type "Business") with the Instagram product; paste the
    # App ID + secret here via API_META_APP_ID / API_META_APP_SECRET in .env.
    meta_app_id: str = ""
    meta_app_secret: str = ""
    # The OAuth callback. Meta requires HTTPS, so in local dev set this to your
    # cloudflared/ngrok HTTPS URL + "/auth/instagram/callback".
    instagram_redirect_uri: str = "https://localhost:8000/auth/instagram/callback"
    # Scopes: business_basic = read profile + media (Reels). Add
    # instagram_business_manage_insights later for watch-time/saves metrics.
    instagram_scopes: str = "instagram_business_basic"
    instagram_graph_version: str = "v21.0"


api_settings = ApiSettings()
