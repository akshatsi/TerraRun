"""
TerraRun — FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, leaderboard, runs, territory

app = FastAPI(
    title=settings.APP_NAME,
    description="Gamified running app — capture territory by running 🏃‍♂️🗺️",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS (allow frontend dev server) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js / Vite dev
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ──
app.include_router(auth.router)
app.include_router(runs.router)
app.include_router(territory.router)
app.include_router(leaderboard.router)


@app.get("/", tags=["health"])
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "version": "0.1.0"}


@app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy"}
