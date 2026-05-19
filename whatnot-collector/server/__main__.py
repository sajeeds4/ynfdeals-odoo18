"""Entry point — run with: python -m server."""

import uvicorn

from app.config import settings
from .whatnot_reviews import start_review_autoscrape_scheduler


def main():
    print(f"Whatnot Runtime API starting on http://{settings.api_host}:{settings.api_port}")
    start_review_autoscrape_scheduler()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
    )


if __name__ == "__main__":
    main()
