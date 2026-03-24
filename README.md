# 🏃 TerraRun — Gamified Territory‑Capture Running App

> Run more. Own the map. Compete with your city.

TerraRun turns boring running into a **territory‑capture game**. Every run you take gets tracked via GPS and converts the path you cover into territory on a shared city map. The more you run, the bigger your territory grows — and you can steal territory from other runners!

---

## 🗂️ Repository Structure

```
TerraRun/
├── docker-compose.yml          # PostgreSQL + PostGIS + Backend
├── .env.example                # Environment variable template
│
├── backend/                    # FastAPI (Python 3.11+)
│   ├── app/
│   │   ├── main.py             # App entry point
│   │   ├── config.py           # Settings from env vars
│   │   ├── database.py         # Async SQLAlchemy + PostGIS
│   │   ├── models/             # ORM models (User, Run, Territory, Badge)
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── routers/            # API route handlers
│   │   ├── services/           # Business logic layer
│   │   └── utils/              # JWT, geo helpers, dependencies
│   ├── alembic/                # DB migrations
│   ├── Dockerfile
│   └── requirements.txt
│
└── frontend/                   # (Coming next) Next.js + Mapbox
```

---

## 🚀 Quick Start

### Prerequisites

- **Docker** & **Docker Compose** installed
- (Optional) Python 3.11+ if running backend outside Docker

### 1. Clone & configure

```bash
git clone <repo-url>
cd TerraRun
cp .env.example .env
# Edit .env if you want to change defaults
```

### 2. Start services

```bash
docker compose up --build
```

This starts:
- **PostgreSQL + PostGIS** on port `5432`
- **FastAPI backend** on port `8000` (with hot‑reload)

### 3. Run database migrations

```bash
docker compose exec backend alembic upgrade head
```

### 4. Explore the API

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/register` | Create account (email, username, password) |
| `POST` | `/auth/login` | Login → access + refresh tokens |
| `POST` | `/auth/refresh` | Refresh access token |
| `GET`  | `/auth/me` | Current user profile |
| `POST` | `/runs` | Submit run with GPS track |
| `GET`  | `/runs` | List user's runs |
| `GET`  | `/runs/:id` | Single run details |
| `GET`  | `/territory/me` | User's territory polygon |
| `GET`  | `/territory/map` | All territories in a bounding box |
| `GET`  | `/leaderboard/global` | Top users by territory area |
| `GET`  | `/leaderboard/local` | Top users in a city |

---

## 🔑 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://intvl:intvl_secret@db:5432/intvl` | Async Postgres URL |
| `JWT_SECRET_KEY` | `change-me` | Secret for signing JWTs |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |

---

## 🧠 Territory Engine

1. After run → GPS points → `LINESTRING`
2. Buffer by ~15 m → thin `POLYGON` strip
3. Union with user's existing `MULTIPOLYGON`
4. **Overlaps:** Last‑write‑wins — new runner takes contested area
5. `ST_Area` recalculates territory → feeds leaderboard

---

## 📦 Tech Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, SQLAlchemy 2.0 (async), Alembic |
| Database | PostgreSQL 15 + PostGIS 3 |
| Geo | Shapely, GeoAlchemy2 |
| Auth | JWT (python‑jose) + bcrypt (passlib) |
| Frontend | Next.js (coming soon) |

---

## 🛣️ Roadmap

- [x] Backend API + Auth
- [x] Territory engine
- [x] Leaderboard
- [x] Badges
- [ ] Frontend (Next.js + Mapbox)
- [ ] Live GPS tracking (WebSocket)
- [ ] Social features
- [ ] Mobile wrapper (Capacitor)
