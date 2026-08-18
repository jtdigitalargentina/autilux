from __future__ import annotations

import re
from typing import Any
from urllib.parse import urldefrag


SIGNAL_PATTERNS = {
    "fleet": (
        r"\bflota\b",
        r"\bfleet\b",
        r"\bveh[ií]cul(?:o|os|ar)\b",
        r"\bcami[oó]n(?:es)?\b",
        r"\butilitari(?:o|os)\b",
        r"\btransportista(?:s)?\b",
        r"\btransporte\b",
        r"\bbiodi[eé]sel\b",
        r"\bcombustible(?:s)?\b",
        r"\bkil[oó]metro(?:s)?\b",
        r"\bkm\b",
    ),
    "infrastructure": (
        r"\binfraestructura\b",
        r"\bcargador(?:es)?\b",
        r"\bcarga el[eé]ctrica\b",
        r"\bestaci[oó]n(?:es)? de carga\b",
        r"\benerg[ií]a\b",
        r"\bpotencia\b",
        r"\bsubestaci[oó]n(?:es)?\b",
    ),
    "sustainability": (
        r"\bsustentabilidad\b",
        r"\bsostenibilidad\b",
        r"\bmovilidad sustentable\b",
        r"\bmovilidad sostenible\b",
        r"\bhuella de carbono\b",
        r"\bcarbono\b",
        r"\bemisiones?\b",
        r"\bdescarbonizaci[oó]n\b",
        r"\besg\b",
        r"\benerg[ií]a renovable\b",
    ),
    "growth": (
        r"\bcrecimiento\b",
        r"\bcreciendo\b",
        r"\binversi[oó]n\b",
        r"\bexpansi[oó]n\b",
        r"\bnueva unidad\b",
        r"\bnuevas? plantas?\b",
        r"\bsucursales\b",
        r"\bhubs?\b",
        r"\bclientes\b",
    ),
}


STRONG_PATTERNS = (
    r"\bflota\b",
    r"\bveh[ií]culos?\b",
    r"\bbiodi[eé]sel\b",
    r"\bmovilidad sustentable\b",
    r"\bmovilidad sostenible\b",
    r"\bhuella de carbono\b",
    r"\bemisiones?\b",
    r"\bdescarbonizaci[oó]n\b",
    r"\bcarga el[eé]ctrica\b",
    r"\bcargadores?\b",
    r"\bestaci[oó]n(?:es)? de carga\b",
    r"\binversi[oó]n\b",
)


NAVIGATION_PHRASES = (
    "seguir envíos",
    "hacer envíos",
    "ver mis envíos",
    "preguntas frecuentes",
    "iniciá sesión",
    "buscar sucursal",
    "ver tarifas",
)


def _normalize_space(value: str) -> str:
    return " ".join((value or "").split())


def _split_fragments(text: str) -> list[str]:
    normalized = text.replace("\r", "\n")

    parts = re.split(
        r"(?:\n{2,}|(?<=[.!?])\s+)",
        normalized,
    )

    return [
        _normalize_space(part)
        for part in parts
        if _normalize_space(part)
    ]


def _categories(fragment: str) -> list[str]:
    categories: list[str] = []

    for category, patterns in SIGNAL_PATTERNS.items():
        if any(
            re.search(pattern, fragment, re.IGNORECASE)
            for pattern in patterns
        ):
            categories.append(category)

    return categories


def _score_fragment(
    fragment: str,
    categories: list[str],
) -> int:
    score = 0
    lowered = fragment.casefold()

    score += len(categories) * 3

    strong_matches = sum(
        1
        for pattern in STRONG_PATTERNS
        if re.search(pattern, fragment, re.IGNORECASE)
    )
    score += strong_matches * 6

    if re.search(r"\d", fragment):
        score += 4

    if re.search(
        r"\b(?:mill[oó]n|millones|%|km|veh[ií]culos?|clientes|env[ií]os)\b",
        fragment,
        re.IGNORECASE,
    ):
        score += 4

    if 60 <= len(fragment) <= 700:
        score += 2

    if len(fragment) < 35:
        score -= 5

    navigation_hits = sum(
        phrase in lowered
        for phrase in NAVIGATION_PHRASES
    )

    score -= navigation_hits * 4

    return score


def extract_evidence_from_pages(
    pages: list[dict[str, Any]],
    max_items: int = 24,
    max_chars_per_item: int = 700,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for page in pages:
        url = urldefrag(str(page.get("url") or "").strip()).url
        title = str(page.get("title") or "").strip()
        text = str(page.get("text") or "")

        if not text:
            continue

        for fragment in _split_fragments(text):
            categories = _categories(fragment)

            if not categories:
                continue

            compact = fragment[:max_chars_per_item]

            if len(compact) < 20:
                continue

            key = (
                url,
                compact.casefold(),
            )

            if key in seen:
                continue

            seen.add(key)

            score = _score_fragment(
                compact,
                categories,
            )

            if score <= 0:
                continue

            candidates.append(
                {
                    "source_url": url,
                    "source_title": title,
                    "categories": categories,
                    "evidence": compact,
                    "_score": score,
                }
            )

    candidates.sort(
        key=lambda item: (
            item["_score"],
            len(item["evidence"]),
        ),
        reverse=True,
    )

    selected = candidates[:max_items]

    for item in selected:
        item.pop("_score", None)

    return selected


def extract_company_evidence(
    collected: dict[str, Any],
) -> dict[str, Any]:
    browser = collected.get("browser") or {}
    http = collected.get("http") or {}

    if browser.get("pages"):
        source = "browser"
        pages = browser["pages"]
    else:
        source = "http"
        pages = http.get("pages") or []

    items = extract_evidence_from_pages(pages)

    total_chars = sum(
        len(item["evidence"])
        for item in items
    )

    return {
        "source": source,
        "items": items,
        "items_count": len(items),
        "source_pages": len(pages),
        "evidence_chars": total_chars,
    }
