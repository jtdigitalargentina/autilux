from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_username
from app.db.session import get_db
from app.crud.users import get_by_username
from app.schemas.user import UserMe

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get("/me", response_model=UserMe)
def me(
    username: str = Depends(get_current_username),
    db: Session = Depends(get_db),
):
    user = get_by_username(db, username)

    return user
