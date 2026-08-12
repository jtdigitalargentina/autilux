import json
import urllib.error
import urllib.request
from typing import Any
from langfuse import get_client

from app.core.settings import settings


SYSTEM_PROMPT = """
Sos el Company Research Agent de Autilux, una empresa de movilidad eléctrica B2B.
Analizá únicamente la información proporcionada y no inventes hechos ni fuentes.
Evaluá oportunidades de electrificación de flota, vehículos corporativos,
infraestructura de carga y análisis TCO.

Respondé exclusivamente con un objeto JSON válido:
{
  "summary": "resumen breve",
  "fleet_signal": true,
  "infrastructure_signal": true,
  "sustainability_signal": false,
  "growth_signal": false,
  "fit": "HIGH",
  "score": 75,
  "reasons": ["razón verificable"],
  "missing_information": ["dato faltante"],
  "recommended_next_step": "próxima acción"
}

fit debe ser LOW, MEDIUM, HIGH o HOT. score debe estar entre 0 y 100.
Si no hay evidencia suficiente, bajá el score y enumerá los datos faltantes.
""".strip()


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[1:-1]).strip()

    result = json.loads(cleaned)
    if not isinstance(result, dict):
        raise ValueError("Kimi response must be a JSON object")
    return result


def research_company(input_data: dict[str, Any] | None) -> dict[str, Any]:
    if not settings.KIMI_API_KEY:
        raise RuntimeError("KIMI_API_KEY is not configured")
    if not input_data:
        raise ValueError("input_data is required for company research")

    body = json.dumps({
        "model": settings.KIMI_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)},
        ],
        "max_tokens": 4000,
    }, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(
        f"{settings.KIMI_BASE_URL}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {settings.KIMI_API_KEY}",
            "Content-Type": "application/json",
        },
    )

    langfuse = get_client()

    with langfuse.start_as_current_observation(
        as_type="generation",
        name="kimi-company-research",
        model=settings.KIMI_MODEL,
        input={
            "system_prompt": SYSTEM_PROMPT,
            "input_data": input_data,
        },
        model_parameters={
            "max_tokens": 4000,
            "response_format": "json_object",
        },
    ) as generation:
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Kimi HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Kimi connection failed: {exc.reason}") from exc

        message = payload["choices"][0]["message"]
        usage = payload.get("usage", {})
        completion_details = usage.get("completion_tokens_details") or {}

        generation.update(
            output=message.get("content"),
            model=payload.get("model", settings.KIMI_MODEL),
            usage_details={
                "input": int(usage.get("prompt_tokens") or 0),
                "output": int(usage.get("completion_tokens") or 0),
                "total": int(usage.get("total_tokens") or 0),
            },
            metadata={
                "provider": "kimi",
                "reasoning_tokens": int(
                    completion_details.get("reasoning_tokens") or 0
                ),
            },
        )

        result = _parse_json(message.get("content") or "")
        result["_runtime"] = {
            "provider": "kimi",
            "model": payload.get("model", settings.KIMI_MODEL),
            "usage": usage,
        }
        return result
