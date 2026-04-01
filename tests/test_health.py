def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_openapi_docs(client):
    r = client.get("/docs")
    assert r.status_code == 200


def test_noiseport_stub_disabled(client):
    r = client.get("/auth/noiseport/login")
    assert r.status_code == 501
