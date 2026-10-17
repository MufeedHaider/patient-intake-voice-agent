"""Application settings, read from environment variables (never hard-coded)."""
import os


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./patients.db")
    # Render and Neon hand out "postgres://" or "postgresql://" URLs.
    # SQLAlchemy needs the driver name to use psycopg (v3).
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _database_url()

# Optional shared secret. When set, the /vapi/webhook endpoint only accepts
# requests carrying it in the X-Vapi-Secret header (or as a Bearer token).
VAPI_SECRET = os.getenv("VAPI_SECRET", "")

# Insert two demo patients on first start-up when the table is empty.
SEED_DATA = os.getenv("SEED_DATA", "true").lower() == "true"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
