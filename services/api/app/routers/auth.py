from datetime import timedelta

from fastapi import APIRouter, HTTPException

from app.schemas.auth import LoginRequest
from app.core.security import (
    create_access_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Usuario temporal para desarrollo
FAKE_USER = {
    "username": "admin",
    # contraseña: admin123
    "password_hash": "$2b$12$NNdIUsfgxdAwmMNP0opYnOJn98qYVt0bUwzqfYrs9/wUyfl2Pczxy",
}


@router.post("/login")
def login(data: LoginRequest):

    if data.username != FAKE_USER["username"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(data.password, FAKE_USER["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(
        {"sub": data.username},
        expires_delta=timedelta(minutes=60),
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }
