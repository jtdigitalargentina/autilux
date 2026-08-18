import json
import urllib.error
import urllib.request
from typing import Any

from langfuse import get_client

from app.core.settings import settings


SYSTEM_PROMPT = """
Sos el Company Research Agent de Autilux, una empresa de movilidad eléctrica B2B.

Tu tarea es evaluar oportunidades de:
- electrificación de flota,
- vehículos corporativos,
- infraestructura de carga,
- análisis TCO,
- sustentabilidad y descarbonización vinculadas a movilidad.

Usá únicamente la información proporcionada en:
- company_input
- collected_evidence

No inventes hechos, cantidades, fuentes ni características de la empresa.

Reglas importantes:
1. Un dato puede considerarse confirmado solamente si aparece en la evidencia recolectada.
2. No conviertas inferencias sectoriales en hechos confirmados.
3. Por ejemplo, que una empresa sea logística no demuestra por sí solo que tenga una flota propia.
4. Si una conclusión es una hipótesis o inferencia, indicá explícitamente que lo es.
5. Si existe una URL asociada a una evidencia relevante, conservála como source_url.
6. Si no hay evidencia suficiente, bajá el score y enumerá la información faltante.

Respondé exclusivamente con un objeto JSON válido con esta estructura:

{
  "summary": "resumen breve",
  "fleet_signal": false,
  "infrastructure_signal": false,
  "sustainability_signal": false,
  "growth_signal": false,
  "fit": "MEDIUM",
  "score": 50,
  "reasons": [
    "razón verificable"
  ],
  "signals": [
    {
      "type": "fleet",
      "confidence": "confirmed",
      "evidence": "texto breve que respalda la señal",
      "source_url": "https://..."
    }
  ],
  "hypotheses": [
    "hipótesis o inferencia que todavía requiere validación"
  ],
  "missing_information": [
    "dato faltante"
  ],
  "recommended_next_step": "próxima acción"
}

Los valores permitidos para confidence son:
- confirmed
- inferred

fit debe ser:
- LOW
- MEDIUM
- HIGH
- HOT

score debe estar entre 0 y 100.
""".strip()


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()

    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[1:-1]).strip()

    result = json.loads(cleaned)

    if not isinstance(result, dict):
        raise ValueError("Kimi response must be a JSON object")

    return result


def research_company(
    input_data: dict[str, Any] | None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not settings.KIMI_API_KEY:
        raise RuntimeError("KIMI_API_KEY is not configured")

    if not input_data:
        raise ValueError("input_data is required for company research")

    research_payload = {
        "company_input": input_data,
        "collected_evidence": evidence or {},
    }

    body = json.dumps(
        {
            "model": settings.KIMI_MODEL,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        research_payload,
                        ensure_ascii=False,
                    ),
                },
            ],
            "max_tokens": 4000,
        },
        ensure_ascii=False,
    ).encode("utf-8")

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
            "research_payload": research_payload,
        },
        model_parameters={
            "max_tokens": 4000,
            "response_format": "json_object",
        },
    ) as generation:
        try:
            with urllib.request.urlopen(
                request,
                timeout=120,
            ) as response:
                payload = json.load(response)

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            raise RuntimeError(
                f"Kimi HTTP {exc.code}: {detail}"
            ) from exc

        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Kimi connection failed: {exc.reason}"
            ) from exc

        message = payload["choices"][0]["message"]
        usage = payload.get("usage", {})
        completion_details = (
            usage.get("completion_tokens_details") or {}
        )

        generation.update(
            output=message.get("content"),
            model=payload.get(
                "model",
                settings.KIMI_MODEL,
            ),
            usage_details={
                "input": int(
                    usage.get("prompt_tokens") or 0
                ),
                "output": int(
                    usage.get("completion_tokens") or 0
                ),
                "total": int(
                    usage.get("total_tokens") or 0
                ),
            },
            metadata={
                "provider": "kimi",
                "reasoning_tokens": int(
                    completion_details.get(
                        "reasoning_tokens"
                    )
                    or 0
                ),
            },
        )

        result = _parse_json(
            message.get("content") or ""
        )

        result["_runtime"] = {
            "provider": "kimi",
            "model": payload.get(
                "model",
                settings.KIMI_MODEL,
            ),
            "usage": usage,
        }

        return result
