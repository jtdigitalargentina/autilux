from fastapi import APIRouter
from app.core.settings import settings

router = APIRouter()


@router.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "ok"
    }
