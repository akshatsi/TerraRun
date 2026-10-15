import logging
import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
import bcrypt

logger = logging.getLogger(__name__)

PLACEHOLDER_SECRET_KEY = "change-this-to-a-long-random-secret"
DEV_SECRET_KEY = "dev-only-insecure-secret-never-use-in-production"


def _load_secret_key() -> str:
    key = os.getenv("SECRET_KEY", "").strip()
    if key and key != PLACEHOLDER_SECRET_KEY:
        return key

    if os.getenv("APP_ENV", "").strip().lower() == "development":
        logger.warning("SECRET_KEY is not set; using the insecure development key.")
        return DEV_SECRET_KEY

    raise RuntimeError(
        "SECRET_KEY is missing or still the placeholder. Set it to a long random "
        "value (for example: openssl rand -hex 32). For local work only, set "
        "APP_ENV=development to use an insecure fallback key."
    )


SECRET_KEY = _load_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception:
        return False


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return {}
