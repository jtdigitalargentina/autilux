import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.integrations.twenty.client import twenty_client


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().strip().split())


def digits(value: Any) -> str:
    return "".join(re.findall(r"\d", str(value or "")))


def extract_contact(value: str) -> tuple[str | None, str | None]:
    email_match = EMAIL_RE.search(value or "")
    email = email_match.group(0).casefold() if email_match else None

    without_email = EMAIL_RE.sub(" ", value or "")
    candidates = re.findall(r"\+?[\d()\s.-]{7,}", without_email)
    phone = None
    for candidate in candidates:
        candidate_digits = digits(candidate)
        if 7 <= len(candidate_digits) <= 16:
            phone = candidate_digits
            break

    return email, phone


def unwrap(response: dict[str, Any], key: str) -> list[dict[str, Any]]:
    data = response.get("data") or {}
    collection = data.get(key) or []
    return collection if isinstance(collection, list) else []


def read_rows(source: Path) -> list[dict[str, str]]:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        return [
            {key: (value or "").strip() for key, value in row.items() if key}
            for row in reader
            if any((value or "").strip() for value in row.values() if value)
        ]


def parse_number(value: str) -> int | float | None:
    cleaned = (value or "").strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def parse_captured_at(value: str) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    for format_string in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(cleaned, format_string)
            return parsed.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass
    return None


def created_record(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("id"):
        return response
    data = response.get("data") or {}
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, dict) and value.get("id"):
                return value
    raise RuntimeError("Twenty did not return a created record id")


def custom_fields_available() -> tuple[bool, list[str]]:
    response = twenty_client._request("GET", "/rest/metadata/objects?limit=100")
    objects = {item["nameSingular"]: item for item in response.get("data", [])}
    required = {
        "company": {
            "autiluxLeadScore",
            "autiluxFit",
            "autiluxResearchSummary",
            "autiluxSignals",
            "vehicleNotes",
            "companyQuality",
        },
        "person": {
            "sourceScore",
            "productInterest",
            "leadSource",
            "sharedBy",
            "capturedAt",
        },
    }
    missing = []
    for object_name, names in required.items():
        existing = {field["name"] for field in objects[object_name].get("fields", [])}
        missing.extend(f"{object_name}.{name}" for name in sorted(names - existing))
    return not missing, missing


def existing_crm_indexes() -> dict[str, Any]:
    companies_response = twenty_client.list_companies(limit=500)
    people_response = twenty_client.list_people(limit=500)
    companies = unwrap(companies_response, "companies")
    people = unwrap(people_response, "people")

    company_by_name = {
        normalize(company.get("name")): company
        for company in companies
        if normalize(company.get("name"))
    }

    person_emails = set()
    person_phones = set()
    person_name_company = set()
    for person in people:
        emails = person.get("emails") or {}
        phones = person.get("phones") or {}
        name = person.get("name") or {}

        primary_email = normalize(emails.get("primaryEmail"))
        if primary_email:
            person_emails.add(primary_email)

        primary_phone = digits(phones.get("primaryPhoneNumber"))
        if primary_phone:
            person_phones.add(primary_phone)

        full_name = normalize(
            f'{name.get("firstName", "")} {name.get("lastName", "")}'
        )
        company_id = str(person.get("companyId") or "")
        if full_name:
            person_name_company.add((full_name, company_id))

    return {
        "companies": companies,
        "people": people,
        "company_by_name": company_by_name,
        "person_emails": person_emails,
        "person_phones": person_phones,
        "person_name_company": person_name_company,
    }


def build_dry_run(rows: list[dict[str, str]], crm: dict[str, Any]) -> dict[str, Any]:
    rejected = Counter()
    company_rows: dict[str, list[dict[str, str]]] = {}

    for row in rows:
        company_key = normalize(row.get("Empresa"))
        if not company_key:
            rejected["missing_company"] += 1
            continue
        company_rows.setdefault(company_key, []).append(row)

    existing_company_keys = set(crm["company_by_name"])
    companies_to_create = set(company_rows) - existing_company_keys
    companies_to_reuse = set(company_rows) & existing_company_keys

    planned_person_keys = set()
    people_to_create = 0
    people_existing = 0
    people_without_contact = 0
    duplicate_people_in_file = 0

    for company_key, grouped_rows in company_rows.items():
        existing_company = crm["company_by_name"].get(company_key)
        company_id = str((existing_company or {}).get("id") or f"NEW:{company_key}")

        for row in grouped_rows:
            person_name = normalize(row.get("Persona"))
            email, phone = extract_contact(row.get("Contacto", ""))

            if not person_name and not email and not phone:
                rejected["no_person_or_contact"] += 1
                continue
            if not email and not phone:
                people_without_contact += 1

            if email:
                key = ("email", email)
                exists = email in crm["person_emails"]
            elif phone:
                key = ("phone", phone)
                exists = phone in crm["person_phones"]
            else:
                key = ("name_company", person_name, company_id)
                exists = (person_name, company_id) in crm["person_name_company"]

            if key in planned_person_keys:
                duplicate_people_in_file += 1
                continue
            planned_person_keys.add(key)

            if exists:
                people_existing += 1
            else:
                people_to_create += 1

    return {
        "mode": "dry-run",
        "sourceRows": len(rows),
        "crmBefore": {
            "companies": len(crm["companies"]),
            "people": len(crm["people"]),
        },
        "companies": {
            "uniqueInAcceptedRows": len(company_rows),
            "wouldCreate": len(companies_to_create),
            "wouldReuse": len(companies_to_reuse),
            "duplicateRowsConsolidated": sum(
                max(0, len(group) - 1) for group in company_rows.values()
            ),
        },
        "people": {
            "wouldCreate": people_to_create,
            "wouldReuse": people_existing,
            "duplicateRowsConsolidated": duplicate_people_in_file,
            "withoutEmailOrPhone": people_without_contact,
        },
        "rejected": dict(rejected),
        "applyAllowed": True,
        "applyBlocker": None,
        "requiredCustomFields": [
            "sourceScore",
            "vehicleNotes",
            "productInterest",
            "companyQuality",
            "leadSource",
            "sharedBy",
            "capturedAt",
        ],
    }


def apply_rows(rows: list[dict[str, str]], crm: dict[str, Any]) -> dict[str, Any]:
    report = {
        "mode": "apply",
        "sourceRows": len(rows),
        "companiesCreated": 0,
        "companiesUpdated": 0,
        "companiesReused": 0,
        "peopleCreated": 0,
        "peopleReused": 0,
        "rowsRejected": Counter(),
        "createdCompanyIds": [],
        "createdPersonIds": [],
    }

    company_by_name = dict(crm["company_by_name"])
    planned_people = set()

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        company_key = normalize(row.get("Empresa"))
        if not company_key:
            report["rowsRejected"]["missing_company"] += 1
            continue
        grouped.setdefault(company_key, []).append(row)

    for company_key, company_rows in grouped.items():
        representative = company_rows[0]
        vehicle_values = list(
            dict.fromkeys(row.get("Vehículos", "") for row in company_rows if row.get("Vehículos"))
        )
        quality_rank = {"baja": 1, "media": 2, "alta": 3}
        quality_values = [row.get("Calidad empresa", "") for row in company_rows]
        company_quality = max(
            quality_values,
            key=lambda value: quality_rank.get(normalize(value), 0),
            default="",
        )

        company_payload = {
            "name": representative["Empresa"],
            "vehicleNotes": " | ".join(vehicle_values)[:5000] or None,
            "companyQuality": company_quality or None,
        }
        company_payload = {
            key: value for key, value in company_payload.items() if value is not None
        }

        company = company_by_name.get(company_key)
        if company:
            update_payload = {
                key: value for key, value in company_payload.items() if key != "name"
            }
            if update_payload:
                twenty_client._request(
                    "PATCH",
                    f'/rest/companies/{company["id"]}',
                    update_payload,
                )
                report["companiesUpdated"] += 1
            else:
                report["companiesReused"] += 1
        else:
            response = twenty_client._request("POST", "/rest/companies", company_payload)
            company = created_record(response)
            company_by_name[company_key] = company
            report["companiesCreated"] += 1
            report["createdCompanyIds"].append(company["id"])

        company_id = str(company["id"])

        for row in company_rows:
            person_name = (row.get("Persona") or "").strip()
            email, phone = extract_contact(row.get("Contacto", ""))
            if not person_name and not email and not phone:
                report["rowsRejected"]["no_person_or_contact"] += 1
                continue

            normalized_name = normalize(person_name)
            if email:
                person_key = ("email", email)
                exists = email in crm["person_emails"]
            elif phone:
                person_key = ("phone", phone)
                exists = phone in crm["person_phones"]
            else:
                person_key = ("name_company", normalized_name, company_id)
                exists = (
                    normalized_name,
                    company_id,
                ) in crm["person_name_company"]

            if person_key in planned_people or exists:
                report["peopleReused"] += 1
                continue
            planned_people.add(person_key)

            payload: dict[str, Any] = {
                "name": {
                    "firstName": person_name or "Contacto feria",
                    "lastName": "",
                },
                "companyId": company_id,
                "sourceScore": parse_number(row.get("Score", "")),
                "productInterest": row.get("Producto") or None,
                "leadSource": (
                    f'Feria 2026 | {row.get("Origen")}'
                    if row.get("Origen")
                    else "Feria 2026"
                ),
                "sharedBy": row.get("Compartido por") or None,
                "capturedAt": parse_captured_at(row.get("Fecha", "")),
            }
            if email:
                payload["emails"] = {
                    "primaryEmail": email,
                    "additionalEmails": [],
                }
            if phone:
                payload["phones"] = {
                    "primaryPhoneNumber": phone,
                    "primaryPhoneCallingCode": "",
                    "primaryPhoneCountryCode": "",
                    "additionalPhones": [],
                }

            payload = {key: value for key, value in payload.items() if value is not None}
            response = twenty_client._request("POST", "/rest/people", payload)
            person = created_record(response)
            report["peopleCreated"] += 1
            report["createdPersonIds"].append(person["id"])
            if email:
                crm["person_emails"].add(email)
            if phone:
                crm["person_phones"].add(phone)
            if normalized_name:
                crm["person_name_company"].add((normalized_name, company_id))

    report["rowsRejected"] = dict(report["rowsRejected"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Import CSV leads into Twenty CRM")
    parser.add_argument("source", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--confirm-all", action="store_true")
    args = parser.parse_args()

    if not args.source.is_file():
        raise SystemExit(f"CSV not found: {args.source}")

    rows = read_rows(args.source)
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be positive")
        rows = rows[: args.limit]

    crm = existing_crm_indexes()
    fields_ok, missing_fields = custom_fields_available()
    if not fields_ok:
        raise SystemExit(f"Missing Twenty custom fields: {', '.join(missing_fields)}")

    if args.apply:
        if args.limit is None and not args.confirm_all:
            raise SystemExit("Full import requires --confirm-all")
        result = apply_rows(rows, crm)
    else:
        result = build_dry_run(rows, crm)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
