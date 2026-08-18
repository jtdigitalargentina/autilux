from __future__ import annotations

from collections import deque
from typing import Any
from urllib.parse import urldefrag, urlparse

from playwright.sync_api import sync_playwright


RELEVANT_KEYWORDS = (
    "about",
    "empresa",
    "nosotros",
    "sustent",
    "sostenib",
    "esg",
    "flota",
    "fleet",
    "logistica",
    "logística",
    "operaciones",
    "operations",
    "infraestructura",
    "infrastructure",
    "corporativo",
    "transportista",
    "career",
    "trabaja",
    "empleo",
    "jobs",
    "news",
    "noticias",
)


def _base_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()

    if host.startswith("www."):
        host = host[4:]

    return host


def _belongs_to_site(
    root_host: str,
    candidate_url: str,
) -> bool:
    host = (urlparse(candidate_url).hostname or "").lower()

    if host.startswith("www."):
        host = host[4:]

    return (
        host == root_host
        or host.endswith("." + root_host)
    )


def _is_relevant_link(
    root_host: str,
    href: str,
    text: str,
) -> bool:
    if not href:
        return False

    if not _belongs_to_site(root_host, href):
        return False

    parsed = urlparse(href)
    path = parsed.path.casefold()

    if path.endswith((".pdf", ".zip", ".doc", ".docx", ".xls", ".xlsx")):
        return False

    searchable = f"{href} {text}".casefold()

    return any(
        keyword in searchable
        for keyword in RELEVANT_KEYWORDS
    )


def collect_browser_research(
    website: str,
    timeout_ms: int = 30000,
    max_chars: int = 30000,
    max_pages: int = 6,
) -> dict[str, Any]:
    root_host = _base_host(website)

    queue = deque([website])
    queued = {website}
    visited: set[str] = set()

    pages: list[dict[str, Any]] = []
    all_links: list[dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000,
            },
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            ),
        )

        page = context.new_page()

        try:
            while queue and len(pages) < max_pages:
                url = queue.popleft()

                if url in visited:
                    continue

                visited.add(url)

                try:
                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )

                    try:
                        page.wait_for_load_state(
                            "networkidle",
                            timeout=10000,
                        )
                    except Exception:
                        pass

                    final_url = page.url

                    if not _belongs_to_site(root_host, final_url):
                        continue

                    title = page.title()

                    body_text = page.locator(
                        "body"
                    ).inner_text(
                        timeout=10000,
                    )

                    links = page.locator(
                        "a"
                    ).evaluate_all(
                        """
                        elements => elements
                            .map(a => ({
                                text: (a.innerText || "").trim(),
                                href: a.href || ""
                            }))
                            .filter(x => x.href)
                        """
                    )

                    pages.append(
                        {
                            "url": final_url,
                            "title": title,
                            "text": body_text[:12000],
                        }
                    )

                    for link in links:
                        href = str(
                            link.get("href") or ""
                        ).strip()

                        href = urldefrag(href).url

                        text = str(
                            link.get("text") or ""
                        ).strip()

                        all_links.append(
                            {
                                "text": text,
                                "href": href,
                            }
                        )

                        if not _is_relevant_link(
                            root_host,
                            href,
                            text,
                        ):
                            continue

                        if (
                            href not in visited
                            and href not in queued
                        ):
                            queue.append(href)
                            queued.add(href)

                except Exception as exc:
                    pages.append(
                        {
                            "url": url,
                            "title": "",
                            "text": "",
                            "error": str(exc),
                        }
                    )

        finally:
            browser.close()

    combined_text_parts = []

    for item in pages:
        text = item.get("text") or ""

        if not text:
            continue

        combined_text_parts.append(
            f"SOURCE URL: {item['url']}\n"
            f"TITLE: {item.get('title', '')}\n"
            f"{text}"
        )

    combined_text = "\n\n".join(
        combined_text_parts
    )[:max_chars]

    unique_links = []
    seen_links = set()

    for link in all_links:
        href = link.get("href")

        if not href or href in seen_links:
            continue

        seen_links.add(href)
        unique_links.append(link)

    first_page = pages[0] if pages else {}

    return {
        "website": website,
        "url": first_page.get("url", website),
        "title": first_page.get("title", ""),
        "text": combined_text,
        "links": unique_links[:200],
        "pages_collected": len(
            [
                item
                for item in pages
                if item.get("text")
            ]
        ),
        "pages": pages,
    }
