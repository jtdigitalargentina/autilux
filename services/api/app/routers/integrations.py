from fastapi import APIRouter, HTTPException

from app.integrations.twenty.client import twenty_client


router = APIRouter(
    prefix="/integrations",
    tags=["integrations"],
)


@router.get("/twenty/health")
def twenty_health():
    try:
        result = twenty_client.list_people(limit=1)

        return {
            "status": "connected",
            "service": "twenty",
            "reachable": True,
            "sample_received": result is not None,
        }

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )
