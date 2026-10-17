import os
import tempfile

# Point the app at a throwaway SQLite file before it is imported.
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["SEED_DATA"] = "false"
os.environ["VAPI_SECRET"] = ""

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def jane():
    return {
        "first_name": "Jane", "last_name": "O'Neil-Smith", "date_of_birth": "04/12/1988",
        "sex": "female", "phone_number": "(732) 555-0123", "address_line_1": "7 Clyde Rd",
        "city": "Somerset", "state": "New Jersey", "zip_code": "08873",
    }
