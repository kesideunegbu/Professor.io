import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import DEFAULT_JWT_SECRET, get_settings
from app.database import Base, engine
from app.routers import auth, compare, professors, reviews, users

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.jwt_secret == DEFAULT_JWT_SECRET:
        log.warning("JWT_SECRET is not set; using an insecure development secret")
    if not settings.gemini_api_key:
        log.warning("GEMINI_API_KEY is not set; AI summaries and comparisons are disabled")
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="Professor.io API",
    description="Professor reviews with Gemini summaries, comparisons and personalized recommendations.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, users.router, professors.router, reviews.router, compare.router):
    app.include_router(router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
