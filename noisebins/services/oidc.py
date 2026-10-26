"""Minimal OpenID Connect relying party (authorization code flow + PKCE).

Works against Noiseport (Spaceport's django-oidc-provider at ``/openid``) and Keycloak realms.
The identity comes from the provider's userinfo endpoint, fetched server-side over TLS with the
access token, so the ID token signature does not need to be checked here.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from noisebins.config import Settings


class OIDCError(Exception):
    pass


@dataclass(frozen=True)
class OIDCEndpoints:
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str


@dataclass(frozen=True)
class OIDCIdentity:
    sub: str
    email: str | None
    email_verified: bool
    name: str | None


_discovery_cache: dict[str, dict] = {}


def http_client() -> httpx.AsyncClient:
    """Factory for outbound calls to the provider (tests swap in a mock transport)."""
    return httpx.AsyncClient(timeout=10.0)


def is_configured(settings: Settings) -> bool:
    has_endpoints = bool(settings.noiseport_issuer) or bool(
        settings.noiseport_authorize_url and settings.noiseport_token_url and settings.noiseport_userinfo_url
    )
    return bool(settings.noiseport_client_id) and has_endpoints


async def get_endpoints(settings: Settings) -> OIDCEndpoints:
    discovered: dict = {}
    issuer = settings.noiseport_issuer.rstrip("/")
    if issuer:
        discovered = _discovery_cache.get(issuer) or await _discover(issuer)

    endpoints = OIDCEndpoints(
        authorization_endpoint=settings.noiseport_authorize_url or discovered.get("authorization_endpoint", ""),
        token_endpoint=settings.noiseport_token_url or discovered.get("token_endpoint", ""),
        userinfo_endpoint=settings.noiseport_userinfo_url or discovered.get("userinfo_endpoint", ""),
    )
    if not all((endpoints.authorization_endpoint, endpoints.token_endpoint, endpoints.userinfo_endpoint)):
        raise OIDCError("OIDC provider is missing an authorization, token, or userinfo endpoint.")
    return endpoints


async def _discover(issuer: str) -> dict:
    url = f"{issuer}/.well-known/openid-configuration"
    try:
        async with http_client() as client:
            r = await client.get(url)
            r.raise_for_status()
            doc = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise OIDCError(f"Could not load OIDC discovery document from {url}: {e}") from e
    _discovery_cache[issuer] = doc
    return doc


def new_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_authorization_url(
    endpoints: OIDCEndpoints,
    settings: Settings,
    *,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.noiseport_client_id,
        "redirect_uri": redirect_uri,
        "scope": settings.noiseport_scopes,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    sep = "&" if "?" in endpoints.authorization_endpoint else "?"
    return f"{endpoints.authorization_endpoint}{sep}{urlencode(params)}"


async def exchange_code(
    endpoints: OIDCEndpoints,
    settings: Settings,
    *,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> str:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.noiseport_client_id,
        "client_secret": settings.noiseport_client_secret,
        "code_verifier": code_verifier,
    }
    try:
        async with http_client() as client:
            r = await client.post(endpoints.token_endpoint, data=data, headers={"Accept": "application/json"})
    except httpx.HTTPError as e:
        raise OIDCError(f"Token request failed: {e}") from e
    if r.status_code != 200:
        raise OIDCError(f"Token endpoint returned {r.status_code}: {r.text[:200]}")
    token = r.json().get("access_token")
    if not token:
        raise OIDCError("Token endpoint response had no access_token.")
    return token


async def fetch_identity(endpoints: OIDCEndpoints, access_token: str) -> OIDCIdentity:
    try:
        async with http_client() as client:
            r = await client.get(endpoints.userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"})
    except httpx.HTTPError as e:
        raise OIDCError(f"Userinfo request failed: {e}") from e
    if r.status_code != 200:
        raise OIDCError(f"Userinfo endpoint returned {r.status_code}: {r.text[:200]}")
    info = r.json()
    sub = info.get("sub")
    if not sub:
        raise OIDCError("Userinfo response had no sub claim.")
    name = info.get("preferred_username") or info.get("name") or info.get("nickname") or info.get("email")
    return OIDCIdentity(
        sub=str(sub),
        email=info.get("email") or None,
        email_verified=info.get("email_verified") is True,
        name=name or None,
    )
