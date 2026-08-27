from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import close_pool, init_pool
from app.routers import health, mvp, profile, route_plans


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_pool()
    yield
    close_pool()


app = FastAPI(
    title="AI Work Partner API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(mvp.router)
app.include_router(route_plans.router)
app.include_router(profile.router)
