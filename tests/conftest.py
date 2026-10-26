import os
import uuid

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from starlette.testclient import TestClient

# Configure before any noisebins imports that build the engine
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg_async://noisebins:noisebins@127.0.0.1:5432/noisebins",
    ),
)
os.environ.setdefault("USERS_JWT_SECRET", "test-jwt-secret-minimum-32-characters-long")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-32chars")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sync_url() -> str:
    return os.environ["DATABASE_URL"].replace("+psycopg_async", "+psycopg", 1)


def _libpq_url() -> str:
    """psycopg.connect wants a plain libpq URL, without SQLAlchemy's +driver suffix."""
    return _sync_url().replace("+psycopg", "", 1)


def pg_ready() -> bool:
    try:
        with psycopg.connect(_libpq_url(), connect_timeout=2) as c:
            c.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def _alembic_upgrade():
    if not pg_ready():
        return
    cfg = Config(os.path.join(_REPO_ROOT, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _sync_url())
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _truncate():
    if not pg_ready():
        return
    with psycopg.connect(_libpq_url()) as c:
        c.execute(
            'TRUNCATE audit_logs, content_history, noisethings, bin_photos, noisebins, noiseplaces, "user" CASCADE'
        )
        c.commit()


@pytest.fixture
def client() -> TestClient:
    from noisebins.main import app

    return TestClient(app)


def register_and_login(
    client: TestClient,
    email: str | None = None,
    password: str = "Str0ngPass!xyz",
) -> tuple[dict[str, str], str]:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r2 = client.post("/auth/jwt/login", data={"username": email, "password": password})
    assert r2.status_code == 200, r2.text
    token = r2.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, email


@pytest.fixture
def auth(client: TestClient):
    headers, _email = register_and_login(client)
    return headers
