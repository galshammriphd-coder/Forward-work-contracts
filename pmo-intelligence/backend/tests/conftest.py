import os, shutil, tempfile
_tmp = tempfile.mkdtemp(prefix="pmo_test_")
os.environ.update(PMO_DATA_DIR=_tmp, PMO_SCHEDULER="0", PMO_SEED_DEMO="1", DATABASE_URL=f"sqlite:///{_tmp}/t.db")
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.seed import DEMO_PASSWORD


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
    shutil.rmtree(_tmp, ignore_errors=True)


@pytest.fixture(scope="session")
def auth(client):
    cache = {}

    def get(who="director"):
        if who not in cache:
            r = client.post("/api/auth/login", json={"email": f"{who}@pmo.local", "password": DEMO_PASSWORD})
            assert r.status_code == 200, r.text
            cache[who] = {"Authorization": f"Bearer {r.json()['token']}"}
        return cache[who]
    return get


@pytest.fixture(scope="session")
def pid(client, auth):
    def get(code):
        return next(p["id"] for p in client.get("/api/projects", headers=auth("admin")).json() if p["code"] == code)
    return get
