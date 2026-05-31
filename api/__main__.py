"""``python -m api`` — run the development server with autoreload."""
from __future__ import annotations

import uvicorn

from api.config import api_settings

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=api_settings.host,
        port=api_settings.port,
        reload=True,
    )
