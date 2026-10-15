# TerraRun

## Features

- User signup and login
- Real-time run tracking using device GPS
- Run timer, distance, and average speed
- Save completed runs to backend
- Run history page
- Leaderboard page
- Home and profile stats
- Map-based tracking using Flutter Map

## Design system

The UI follows the INTVL look: a near-black canvas, a coral-to-magenta brand
gradient, purple for claimed territory, and Plus Jakarta Sans for type.

- `lib/theme/app_theme.dart` has the colour tokens (`AppColors`), the type
  scale (`AppText`) and the dark `ThemeData`.
- `lib/widgets/app_widgets.dart` has the shared pieces: `GradientButton`,
  `SegmentedPill`, `StatBlock`, `AppCard`, `HeroCard`, `Headline` and others.
- `lib/utils/format.dart` formats areas, durations and date keys.

Fonts load through the `google_fonts` package, so the first launch needs a
network connection.

## Tech Stack

### Frontend
- Flutter
- Dart
- Flutter Map
- Geolocator

### Backend
- FastAPI
- Python
- Uvicorn
- PostgreSQL

## Project Structure

```text
fitness_game_app/
│
├── lib/                  # Flutter frontend
├── backend/              # FastAPI backend
├── assets/               # Images/assets
├── android/
├── ios/
├── macos/
├── web/
└── pubspec.yaml
```

## Running locally

```bash
# 1. Clone project
git clone https://github.com/YOUR_USERNAME/TerraRun.git
cd TerraRun

# 2. BACKEND SETUP
cd backend

# Create virtual environment
python3 -m venv ../venv

# Activate (macOS/Linux)
source ../venv/bin/activate

# Install backend dependencies
pip install -r requirements.txt

# Start backend server. It needs PostgreSQL with PostGIS on localhost:5432
# (docker compose up db). APP_ENV=development allows the insecure fallback
# SECRET_KEY; without it the backend refuses to start.
APP_ENV=development python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000


# 3. FIND YOUR LOCAL IP (for mobile testing)
# Run this command:
ifconfig

# Look for something like:
# inet 192.168.x.x  ← this is your IP


# 4. CONFIGURE FRONTEND URL
# Open this file in your code editor:
# lib/config.dart

# Replace its content with:

# ----------------------------------------
# import 'package:flutter/foundation.dart';
#
# class Config {
#   static String get baseUrl {
#     if (kIsWeb) {
#       return 'http://localhost:8000';
#     }
#     return 'http://YOUR_IP:8000';
#   }
# }
# ----------------------------------------

# Replace YOUR_IP with your actual IP
# Example:
# http://192.168.1.5:8000


# 5. FRONTEND SETUP (open new terminal)

cd TerraRun
flutter pub get


# 6. RUN APP

# Run on Chrome (web)
flutter run -d chrome

# OR run on iPhone / Android (same Wi-Fi required)
flutter run

- For mobile: DO NOT use localhost → use your IP
- Phone and laptop must be on same Wi-Fi
- GPS works best on real phone (not Chrome)
```

## Deploying

Nothing needs a source edit per environment. The backend reads environment
variables, and the app reads `--dart-define=API_URL`.

### Database and backend

With Docker, on any host that runs it:

```bash
cp .env.example .env
# Fill in .env: POSTGRES_PASSWORD (openssl rand -hex 24) and SECRET_KEY (openssl rand -hex 32)
docker compose -f docker-compose.prod.yml up -d --build
curl http://localhost:8000/
```

This starts PostGIS and the backend. It publishes only port 8000, mounts no
source, and refuses to start without the two secrets. The app needs an
`https://` address, so put TLS in front of port 8000.

On a server with a domain name, the `https` profile does that with Caddy,
which gets and renews the certificate itself. Add `DOMAIN=api.example.com` and
`BACKEND_BIND=127.0.0.1` to `.env`, point the domain's DNS at the server, open
ports 80 and 443, then run:

```bash
docker compose -f docker-compose.prod.yml --profile https up -d --build
```

With a managed PostgreSQL instead, build and run the backend alone:

```bash
cp backend/.env.example backend/.env   # fill it in
docker build -t terrarun-backend ./backend
docker run -d -p 8000:8000 --env-file backend/.env terrarun-backend
```

| Variable | Meaning |
|----------|---------|
| `DATABASE_URL` | PostgreSQL with PostGIS. `postgres://` and `postgresql://` both work. |
| `SECRET_KEY` | Signs login tokens. The backend will not start if it is empty or the placeholder. |
| `APP_ENV` | `production` (default). `development` allows an insecure fallback key; use it on your own machine only. |
| `CORS_ORIGINS` | Optional, comma-separated. Origins of a deployed web build. localhost is always allowed. |

The backend runs `CREATE EXTENSION IF NOT EXISTS postgis` at start, so its
database role must be allowed to do that. On a managed database, enable PostGIS
yourself first if it is not.

**No migrations.** Tables come from SQLAlchemy `create_all` on each start. It
adds missing tables and never changes existing ones, so a new column on a live
database needs a manual `ALTER TABLE` (or Alembic, which is not set up).
Back up first: `pg_dump`.

### Android

Make a signing key once, and keep it safe (Google Play needs the same key for
every update):

```bash
keytool -genkey -v -keystore ~/terrarun-upload.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
cp android/key.properties.example android/key.properties   # fill it in
```

Then build, with your API address:

```bash
flutter build appbundle --release --dart-define=API_URL=https://api.example.com   # Play Store
flutter build apk --release --dart-define=API_URL=https://api.example.com         # direct install
```

Without `android/key.properties` the release build is signed with the debug
keys. It installs, but the Play Store rejects it. Use an `https://` address;
Android blocks plain `http://` from release builds by default.

#### Test build for a phone on the same Wi-Fi

To try the app with the backend running on your own computer (no domain, no
HTTPS), start the backend, find the computer's address, and build with the
switch that allows plain `http://`:

```bash
ipconfig getifaddr en0
```

```bash
ORG_GRADLE_PROJECT_allowCleartext=true flutter build apk --release --dart-define=API_URL=http://YOUR_IP:8000
```

Then install it on a phone with USB debugging on:

```bash
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

The phone must be on the same Wi-Fi, and the address is fixed into the app:
if your router gives the computer a new one, build again (or reserve the
address in the router). Do not publish a build made with this switch.

### iOS

```bash
flutter build ipa --release --dart-define=API_URL=https://api.example.com
```

This needs a Mac with the full Xcode app (not installed on the Mac this was set
up on; `flutter doctor` reports it) and an Apple Developer account. Open
`ios/Runner.xcworkspace` once, and under Signing & Capabilities pick your team.

### Web

```bash
flutter build web --release --dart-define=API_URL=https://api.example.com
```

Add the site's origin to `CORS_ORIGINS` on the backend.

### Application ID

The id `com.terrarun.app` is a placeholder. Replace it with one you own (a
reverse domain, for example `com.yourname.terrarun`) before the first upload.
A store will not let you change it afterwards. Change it in:

| File | What |
|------|------|
| `android/app/build.gradle.kts` | `namespace` and `applicationId` |
| `android/app/src/main/kotlin/com/terrarun/app/MainActivity.kt` | the `package` line, and move the file to the matching folders |
| `ios/Runner.xcodeproj/project.pbxproj` | `PRODUCT_BUNDLE_IDENTIFIER`, 6 places (or set it in Xcode: Runner target, General) |
| `lib/widgets/map_tiles.dart` | `userAgentPackageName` |

The macOS and Linux projects still use `com.example.*`
(`macos/Runner/Configs/AppInfo.xcconfig`, `macos/Runner.xcodeproj/project.pbxproj`,
`linux/CMakeLists.txt`). Change those only if you ship those targets.

To list every place, run `grep -rIn "com\.terrarun\.app" android ios lib`.

### Map tiles

The map loads tiles from OpenStreetMap's public server. Its usage policy is
for light use, so a public release should use a keyed provider (MapTiler,
Stadia Maps, Carto and others). Change `urlTemplate` in
`lib/widgets/map_tiles.dart`, and show the provider's attribution.
