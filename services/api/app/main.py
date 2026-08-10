from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.settings import settings
from app.db.init_db import init_db

from app.routers import auth
from app.routers import health
from app.routers import root
from app.routers import users
from app.routers import integrations

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

app.include_router(root.router)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(integrations.router)
