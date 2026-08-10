from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_username
from app.integrations.twenty.client import twenty_client


router = APIRouter(
    prefix="/integrations",
    tags=["integrations"],
)


@router.get("/twenty/health")
def twenty_health(
    current_username: str = Depends(get_current_username),
):
    try:
        result = twenty_client.list_people(limit=1)

        return {
            "status": "connected",
            "service": "twenty",
            "reachable": True,
            "sample_received": result is not None,
        }

    except RuntimeError:
        raise HTTPException(
            status_code=502,
            detail="Twenty integration unavailable",
        )

@router.get("/twenty/people")
def twenty_people(
    current_username: str = Depends(get_current_username),
):
    try:
        return twenty_client.list_people(limit=10)
    except RuntimeError:
        raise HTTPException(
            status_code=502,
            detail="Twenty integration unavailable",
        )


@router.get("/twenty/companies")
def twenty_companies(
    current_username: str = Depends(get_current_username),
):
    try:
        return twenty_client.list_companies(limit=10)
    except RuntimeError:
        raise HTTPException(
            status_code=502,
            detail="Twenty integration unavailable",
        )


@router.get("/twenty/opportunities")
def twenty_opportunities(
    current_username: str = Depends(get_current_username),
):
    try:
        return twenty_client.list_opportunities(limit=10)
    except RuntimeError:
        raise HTTPException(
            status_code=502,
            detail="Twenty integration unavailable",
        )
