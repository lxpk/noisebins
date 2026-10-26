import io
import uuid

import pytest

from tests.conftest import pg_ready, register_and_login

pytestmark = pytest.mark.skipif(not pg_ready(), reason="Postgres required")


def test_register_login_smoke_auth(client, auth):
    place = {
        "name": "Shelf A",
        "description": "test",
    }
    r = client.post("/api/v1/places", json=place, headers=auth)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    r2 = client.post(
        "/api/v1/bins",
        json={"title": "Parts", "noiseplace_id": pid, "contents_text": "widgets"},
        headers=auth,
    )
    assert r2.status_code == 201, r2.text
    code = r2.json()["noisecode"]

    pub = client.get(f"/api/v1/bins/{code}")
    assert pub.status_code == 200
    assert pub.json()["title"] == "Parts"
    assert pub.json()["maintainer_email"] is None

    s = client.get("/api/v1/bins/search", params={"q": "widgets"})
    assert s.status_code == 200
    assert len(s.json()) >= 1

    rpatch = client.patch(
        f"/api/v1/bins/{code}",
        json={"contents_text": "gadgets"},
        headers=auth,
    )
    assert rpatch.status_code == 200

    hist = client.get(f"/api/v1/bins/{code}/history", headers=auth)
    assert hist.status_code == 200
    assert len(hist.json()) >= 1

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x00\x00\x00\x01\x01\x00"
        b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    up = client.post(
        f"/api/v1/bins/{code}/photos",
        headers=auth,
        files={"file": ("x.png", io.BytesIO(png), "image/png")},
    )
    assert up.status_code == 201, up.text

    pdf = client.get(f"/api/v1/bins/{code}/label.pdf", headers=auth)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"

    cl = client.post(f"/api/v1/bins/{code}/claim", headers=auth)
    assert cl.status_code == 200

    t = client.post(
        f"/api/v1/bins/{code}/things",
        headers=auth,
        json={"name": "Hammer"},
    )
    assert t.status_code == 201

    sug = client.post(
        f"/api/v1/bins/{code}/suggest-contents",
        headers=auth,
        json={},
    )
    assert sug.status_code == 200
    assert sug.json()["enabled"] is False


def test_claim_transfer_audit(client):
    a, _ = register_and_login(client)
    place = client.post("/api/v1/places", json={"name": "P1"}, headers=a)
    pid = place.json()["id"]
    bresp = client.post(
        "/api/v1/bins",
        json={"title": "Shared", "noiseplace_id": pid},
        headers=a,
    )
    code = bresp.json()["noisecode"]
    _headers_b, email_b = register_and_login(client, email=f"b-{uuid.uuid4().hex[:6]}@example.com")
    cl = client.post(f"/api/v1/bins/{code}/claim", headers=a)
    assert cl.status_code == 200
    tr = client.post(
        f"/api/v1/bins/{code}/transfer",
        headers=a,
        json={"to_user_email": email_b},
    )
    assert tr.status_code == 200


def test_limbo_list(client, auth):
    client.post(
        "/api/v1/bins",
        json={"title": "Old", "status": "limbo"},
        headers=auth,
    )
    r = client.get("/api/v1/bins/limbo", headers=auth)
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_unauth_mutating_returns_401(client):
    r = client.post("/api/v1/places", json={"name": "x"})
    assert r.status_code == 401


def test_suggest_vision_on(monkeypatch, client, auth):
    import noisebins.api.v1.bins as bins_routes
    from noisebins.config import get_settings

    vision_on = get_settings().model_copy(update={"vision_assist_enabled": True})
    monkeypatch.setattr(bins_routes, "get_settings", lambda: vision_on)
    b = client.post("/api/v1/bins", json={"title": "V"}, headers=auth)
    code = b.json()["noisecode"]
    s = client.post(
        f"/api/v1/bins/{code}/suggest-contents",
        headers=auth,
        json={"image_base64": "YXNkZmdoaWo="},
    )
    assert s.status_code == 200
    assert s.json()["enabled"] is True
