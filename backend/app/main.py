import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
from app.routes.auth_routes import router as auth_router
from app.routes.run_routes import router as run_router
from app.routes.stats_routes import router as stats_router
from app.routes.leaderboard_routes import router as leaderboard_router
from app.routes.territory_routes import router as territory_router


Base.metadata.create_all(bind=engine)

app = FastAPI(title="TerraRun API")

# Extra origins for a deployed web build, e.g. "https://app.example.com".
cors_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(run_router)
app.include_router(stats_router)
app.include_router(leaderboard_router)
app.include_router(territory_router)


@app.get("/")
def root():
    return {"message": "TerraRun backend is running"}