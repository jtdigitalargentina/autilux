import json
import unicodedata
from typing import Any
from urllib.parse import urlparse

from app.integrations.twenty.client import twenty_client


CRM_SCORE_THRESHOLD = 60


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().strip().split())


def _normalize_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").casefold()
    return host.removeprefix("www.")


def _record_from_response(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("id"):
        return response
    data = response.get("data") or {}
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, dict) and value.get("id"):
                return value
    raise RuntimeError("Twenty did not return a company id")


def _companies() -> list[dict[str, Any]]:
    response = twenty_client.list_companies(limit=500)
    data = response.get("data") or {}
    companies = data.get("companies") or []
    return companies if isinstance(companies, list) else []


def _find_company(
    companies: list[dict[str, Any]],
    company_name: str,
    website: str,
) -> dict[str, Any] | None:
    website_host = _normalize_url(website)
    normalized_name = _normalize_text(company_name)

    if website_host:
        for company in companies:
            domain = company.get("domainName") or {}
            if _normalize_url(domain.get("primaryLinkUrl")) == website_host:
                return company

    for company in companies:
        if _normalize_text(company.get("name")) == normalized_name:
            return company

    return None


def _signals_payload(research: dict[str, Any]) -> str:
    signals = {
        "fleet": bool(research.get("fleet_signal")),
        "infrastructure": bool(research.get("infrastructure_signal")),
        "sustainability": bool(research.get("sustainability_signal")),
        "growth": bool(research.get("growth_signal")),
        "reasons": research.get("reasons") or [],
        "missing_information": research.get("missing_information") or [],
        "recommended_next_step": research.get("recommended_next_step"),
    }
    return json.dumps(signals, ensure_ascii=False)[:10000]


def sync_company_research(
    input_data: dict[str, Any] | None,
    research: dict[str, Any],
) -> dict[str, Any]:
    source = input_data or {}
    score = int(research.get("score") or 0)

    if source.get("sync_to_crm", True) is False:
        return {"synced": False, "reason": "disabled_by_input"}

    if score < CRM_SCORE_THRESHOLD:
        return {
            "synced": False,
            "reason": "below_threshold",
            "threshold": CRM_SCORE_THRESHOLD,
            "score": score,
        }

    company_name = str(
        source.get("company_name") or source.get("company") or ""
    ).strip()
    if not company_name:
        return {"synced": False, "reason": "missing_company_name", "score": score}

    website = str(source.get("website") or source.get("domain") or "").strip()
    companies = _companies()
    existing = _find_company(companies, company_name, website)

    payload: dict[str, Any] = {
        "name": company_name,
        "autiluxLeadScore": score,
        "autiluxFit": str(research.get("fit") or ""),
        "autiluxResearchSummary": str(research.get("summary") or "")[:10000],
        "autiluxSignals": _signals_payload(research),
    }
    if website:
        payload["domainName"] = {
            "primaryLinkUrl": (
                website if "://" in website else f"https://{website}"
            ),
            "primaryLinkLabel": _normalize_url(website),
            "secondaryLinks": [],
        }

    if existing:
        response = twenty_client._request(
            "PATCH",
            f'/rest/companies/{existing["id"]}',
            payload,
        )
        company = _record_from_response(response)
        action = "updated"
    else:
        response = twenty_client._request("POST", "/rest/companies", payload)
        company = _record_from_response(response)
        action = "created"

    return {
        "synced": True,
        "action": action,
        "company_id": company["id"],
        "score": score,
        "threshold": CRM_SCORE_THRESHOLD,
    }
