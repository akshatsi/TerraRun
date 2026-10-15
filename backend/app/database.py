import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DEFAULT_DATABASE_URL = "postgresql://terrarun:terrarun_secret@localhost:5432/terrarun"


def normalise_database_url(url: str) -> str:
    # Some hosts hand out postgres://, which SQLAlchemy 2 no longer accepts.
    # SQLAlchemy 2.1 also reads a bare postgresql:// as psycopg 3, but
    # requirements.txt installs psycopg2, so name that driver.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


DATABASE_URL = normalise_database_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
