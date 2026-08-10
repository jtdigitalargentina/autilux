from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    get_current_username,
    verify_password,
)
from app.crud.users import get_by_username
from app.db.session import get_db
from app.schemas.auth import LoginRequest
from app.schemas.user import UserMe


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post("/login")
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    user = get_by_username(
        db,
        data.username,
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User inactive",
        )

    if not verify_password(
        data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    token = create_access_token(
        {"sub": user.username},
        expires_delta=timedelta(minutes=60),
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }


@router.get(
    "/me",
    response_model=UserMe,
)
def me(
    username: str = Depends(get_current_username),
    db: Session = Depends(get_db),
):
    user = get_by_username(
        db,
        username,
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User inactive",
        )

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
    }
