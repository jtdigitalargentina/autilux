from __future__ import annotations

from collections import deque
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


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
    "career",
    "trabaja",
    "empleo",
    "jobs",
    "news",
    "noticias",
)


def _normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise ValueError("website is required")

    if "://" not in value:
        value = f"https://{value}"

    return value


def _same_host(base_url: str, candidate_url: str) -> bool:
    base_host = (urlparse(base_url).hostname or "").removeprefix("www.")
    candidate_host = (urlparse(candidate_url).hostname or "").removeprefix("www.")
    return bool(base_host and candidate_host and base_host == candidate_host)


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    text = " ".join(soup.stripped_strings)
    return " ".join(text.split())


def _extract_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()

        if not href or href.startswith(
            ("#", "mailto:", "tel:", "javascript:")
        ):
            continue

        absolute = urljoin(base_url, href)

        if not _same_host(base_url, absolute):
            continue

        searchable = (
            f"{absolute} {anchor.get_text(' ', strip=True)}"
        ).casefold()

        if any(keyword in searchable for keyword in RELEVANT_KEYWORDS):
            links.append(absolute)

    return list(dict.fromkeys(links))


def collect_website_research(
    website: str,
    max_pages: int = 6,
    max_chars_per_page: int = 12000,
) -> dict[str, Any]:
    start_url = _normalize_url(website)

    queue = deque([start_url])
    visited: set[str] = set()
    pages: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(compatible; AutiluxResearchBot/0.1; "
            "+https://autilux.com)"
        )
    }

    with httpx.Client(
        follow_redirects=True,
        timeout=15.0,
        headers=headers,
    ) as client:
        while queue and len(pages) < max_pages:
            url = queue.popleft()

            if url in visited:
                continue

            visited.add(url)

            try:
                response = client.get(url)
                response.raise_for_status()
            except Exception as exc:
                errors.append({
                    "url": url,
                    "error": str(exc),
                })
                continue

            content_type = response.headers.get("content-type", "")

            if "text/html" not in content_type:
                continue

            final_url = str(response.url)
            soup = BeautifulSoup(response.text, "html.parser")
            text = _extract_text(response.text)

            title = ""
            if soup.title and soup.title.string:
                title = soup.title.string.strip()

            if text:
                pages.append({
                    "url": final_url,
                    "title": title,
                    "text": text[:max_chars_per_page],
                })

            if len(pages) < max_pages:
                for link in _extract_links(final_url, response.text):
                    if link not in visited and link not in queue:
                        queue.append(link)

    return {
        "website": start_url,
        "pages_collected": len(pages),
        "pages": pages,
        "errors": errors,
    }
