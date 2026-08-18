from __future__ import annotations

from typing import Any

from langfuse import get_client

from app.research.browser_collector import collect_browser_research
from app.research.web_collector import collect_website_research


MIN_HTTP_TEXT_CHARS = 800


def _http_text_size(result: dict[str, Any]) -> int:
    pages = result.get("pages") or []
    return sum(
        len(str(page.get("text") or ""))
        for page in pages
    )


def collect_company_evidence(
    website: str,
) -> dict[str, Any]:
    langfuse = get_client()

    with langfuse.start_as_current_observation(
        as_type="tool",
        name="website-http-collector",
        input={"website": website},
    ) as http_observation:
        http_result = collect_website_research(
            website,
            max_pages=6,
            max_chars_per_page=10000,
        )

        http_chars = _http_text_size(http_result)

        http_observation.update(
            output={
                "pages_collected": http_result.get("pages_collected", 0),
                "text_chars": http_chars,
                "errors": len(http_result.get("errors") or []),
            }
        )

    use_browser = http_chars < MIN_HTTP_TEXT_CHARS

    browser_result = None

    if use_browser:
        with langfuse.start_as_current_observation(
            as_type="tool",
            name="website-browser-collector",
            input={
                "website": website,
                "reason": "insufficient_http_content",
            },
        ) as browser_observation:
            browser_result = collect_browser_research(
                website,
                max_chars=20000,
            )

            browser_observation.update(
                output={
                    "title": browser_result.get("title"),
                    "text_chars": len(browser_result.get("text") or ""),
                    "links": len(browser_result.get("links") or []),
                    "url": browser_result.get("url"),
                }
            )

    return {
        "website": website,
        "collection_strategy": (
            "browser_fallback"
            if browser_result is not None
            else "http"
        ),
        "http": http_result,
        "browser": browser_result,
    }
