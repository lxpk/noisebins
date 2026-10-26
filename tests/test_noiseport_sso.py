import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from tests.conftest import pg_ready, register_and_login

pytestmark = pytest.mark.skipif(not pg_ready(), reason="Postgres required")

ISSUER = "https://noiseport.test/openid"


class FakeNoiseport:
    """Just enough of an OIDC provider (Noiseport's django-oidc-provider) for the code + PKCE flow."""

    def __init__(self):
        self.userinfo = {"sub": "42", "preferred_username": "tanner"}
        self.challenges: dict[str, str] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{ISSUER}/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "userinfo_endpoint": f"{ISSUER}/userinfo",
                },
            )
        if url == f"{ISSUER}/token":
            form = parse_qs(request.content.decode())
            code = form["code"][0]
            digest = hashlib.sha256(form["code_verifier"][0].encode()).digest()
            challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
            if self.challenges.get(code) != challenge or form["client_secret"][0] != "s3cret":
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": f"at-{code}", "token_type": "bearer"})
        if url == f"{ISSUER}/userinfo":
            assert request.headers["authorization"].startswith("Bearer at-")
            return httpx.Response(200, json=self.userinfo)
        return httpx.Response(404)

    def authorize(self, authorize_url: str) -> tuple[str, str]:
        """Pretend the member is already signed in to Noiseport: approve immediately."""
        q = parse_qs(urlparse(authorize_url).query)
        code = f"code{len(self.challenges)}"
        self.challenges[code] = q["code_challenge"][0]
        return code, q["state"][0]


@pytest.fixture
def noiseport(monkeypatch):
    from noisebins.config import get_settings
    from noisebins.services import oidc

    settings = get_settings()
    monkeypatch.setattr(settings, "noiseport_oauth_enabled", True)
    monkeypatch.setattr(settings, "noiseport_issuer", ISSUER)
    monkeypatch.setattr(settings, "noiseport_client_id", "noisebins")
    monkeypatch.setattr(settings, "noiseport_client_secret", "s3cret")
    monkeypatch.setattr(oidc, "_discovery_cache", {})
    fake = FakeNoiseport()
    monkeypatch.setattr(oidc, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    return fake


def sso_login(client, fake: FakeNoiseport, next_path: str = "/") -> httpx.Response:
    r = client.get("/auth/noiseport/login", params={"next": next_path}, follow_redirects=False)
    assert r.status_code == 302, r.text
    assert r.headers["location"].startswith(f"{ISSUER}/authorize?")
    code, state = fake.authorize(r.headers["location"])
    return client.get("/auth/noiseport/callback", params={"code": code, "state": state}, follow_redirects=False)


def test_sso_login_creates_session_and_returns_to_next(client, noiseport):
    r = sso_login(client, noiseport, "/bins/new")
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/bins/new"

    me = client.get("/users/me")
    assert me.status_code == 200
    assert me.json()["display_name"] == "tanner"
    assert me.json()["email"] == "noiseport-42@sso.noisebins.noisebridge.net"

    home = client.get("/")
    assert "Signed in as" in home.text and "tanner" in home.text


def test_sso_session_can_update_bins_from_browser(client, noiseport):
    sso_login(client, noiseport)
    r = client.post("/bins/new", data={"title": "Soldering irons"}, follow_redirects=False)
    assert r.status_code == 303
    code = r.headers["location"].removeprefix("/b/")
    page = client.get(f"/b/{code}")
    assert "Soldering irons" in page.text

    # Same-origin fetches from pages are authenticated by the cookie too.
    upd = client.patch(f"/api/v1/bins/{code}", json={"contents_text": "Hakko x3"})
    assert upd.status_code == 200, upd.text


def test_repeat_sso_login_reuses_user(client, noiseport):
    sso_login(client, noiseport)
    first = client.get("/users/me").json()["id"]
    client.cookies.clear()
    sso_login(client, noiseport)
    assert client.get("/users/me").json()["id"] == first


def test_logged_out_new_bin_redirects_to_sso(client, noiseport):
    r = client.get("/bins/new", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/auth/noiseport/login?next=/bins/new"
    assert client.post("/bins/new", data={"title": "x"}).status_code == 401


def test_logout_clears_session(client, noiseport):
    sso_login(client, noiseport)
    r = client.post("/auth/logout", follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/users/me").status_code == 401


def test_state_mismatch_rejected(client, noiseport):
    r = client.get("/auth/noiseport/login", follow_redirects=False)
    code, _state = noiseport.authorize(r.headers["location"])
    bad = client.get("/auth/noiseport/callback", params={"code": code, "state": "forged"})
    assert bad.status_code == 400


def test_callback_without_login_cookie_rejected(client, noiseport):
    r = client.get("/auth/noiseport/callback", params={"code": "c", "state": "s"})
    assert r.status_code == 400


def test_open_redirect_blocked(client, noiseport):
    r = sso_login(client, noiseport, "//evil.example/steal")
    assert r.headers["location"] == "/"


def test_verified_email_links_existing_password_account(client, noiseport):
    _headers, email = register_and_login(client)
    noiseport.userinfo = {"sub": "7", "email": email, "email_verified": True, "name": "Pat"}
    sso_login(client, noiseport)
    me = client.get("/users/me").json()
    assert me["email"] == email
    assert me["display_name"] == "Pat"


def test_unverified_email_does_not_take_over_account(client, noiseport):
    _headers, email = register_and_login(client)
    client.cookies.clear()
    noiseport.userinfo = {"sub": "8", "email": email, "email_verified": False}
    r = sso_login(client, noiseport)
    assert r.status_code == 409


def test_provider_error_is_reported(client, noiseport):
    r = client.get(
        "/auth/noiseport/callback", params={"error": "access_denied", "error_description": "Must be an active member."}
    )
    assert r.status_code == 400
    assert "Must be an active member." in r.text
