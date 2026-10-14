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


HOW TO RUN
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
pip install fastapi uvicorn

# Start backend server
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000


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
