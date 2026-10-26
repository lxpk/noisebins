"""Browser single sign-on with Noiseport (or any OIDC provider, e.g. the Noisebridge Keycloak realm).

``GET /auth/noiseport/login?next=/b/ABC`` sends the browser to the provider. Someone already signed
in to Noiseport is bounced straight back to ``/auth/noiseport/callback``, which links or creates the
noisebins user, sets the session cookie, and redirects to ``next``.
"""

from __future__ import annotations

import secrets
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi_users import exceptions
from fastapi_users.jwt import decode_jwt, generate_jwt

from noisebins.config import get_settings
from noisebins.services import oidc
from noisebins.users import UserManager, cookie_backend, get_jwt_strategy, get_user_manager

OAUTH_NAME = "noiseport"
STATE_COOKIE = "noisebins_oidc_state"
STATE_AUDIENCE = "noisebins:oidc-state"
STATE_LIFETIME_SECONDS = 600

router = APIRouter(prefix="/auth/noiseport", tags=["auth"])
session_router = APIRouter(prefix="/auth", tags=["auth"])


def safe_next(next_path: str | None) -> str:
    """Only allow same-site relative paths so ``next`` cannot become an open redirect."""
    if next_path and next_path.startswith("/") and not next_path.startswith("//") and "\\" not in next_path:
        return next_path
    return "/"


def login_path(next_path: str = "/") -> str:
    return f"{router.prefix}/login?next={quote(safe_next(next_path), safe='/')}"


def _redirect_uri() -> str:
    return f"{get_settings().public_base_url.rstrip('/')}{router.prefix}/callback"


def _require_enabled() -> None:
    settings = get_settings()
    if not settings.noiseport_oauth_enabled:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "Noiseport sign-in is disabled. Set NOISEPORT_OAUTH_ENABLED=true and NOISEPORT_ISSUER in .env.",
        )
    if not oidc.is_configured(settings):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Noiseport sign-in needs NOISEPORT_CLIENT_ID and NOISEPORT_ISSUER (or explicit endpoint URLs).",
        )


@router.get("/login")
async def noiseport_login(next: str = "/"):
    _require_enabled()
    settings = get_settings()
    try:
        endpoints = await oidc.get_endpoints(settings)
    except oidc.OIDCError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))

    state = secrets.token_urlsafe(24)
    verifier, challenge = oidc.new_pkce_pair()
    url = oidc.build_authorization_url(
        endpoints, settings, redirect_uri=_redirect_uri(), state=state, code_challenge=challenge
    )
    flow = generate_jwt(
        {"state": state, "verifier": verifier, "next": safe_next(next), "aud": STATE_AUDIENCE},
        settings.secret_key,
        STATE_LIFETIME_SECONDS,
    )
    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        STATE_COOKIE,
        flow,
        max_age=STATE_LIFETIME_SECONDS,
        path=router.prefix,
        secure=settings.session_cookie_secure_effective,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/callback")
async def noiseport_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    user_manager: UserManager = Depends(get_user_manager),
):
    _require_enabled()
    settings = get_settings()
    name = settings.noiseport_display_name

    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name} sign-in failed: {error_description or error}")
    raw_flow = request.cookies.get(STATE_COOKIE)
    if not code or not state or not raw_flow:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name} sign-in expired. Please try again.")
    try:
        flow = decode_jwt(raw_flow, settings.secret_key, [STATE_AUDIENCE])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name} sign-in expired. Please try again.")
    if not secrets.compare_digest(str(flow.get("state", "")), state):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name} sign-in state mismatch. Please try again.")

    try:
        endpoints = await oidc.get_endpoints(settings)
        access_token = await oidc.exchange_code(
            endpoints, settings, code=code, redirect_uri=_redirect_uri(), code_verifier=flow["verifier"]
        )
        identity = await oidc.fetch_identity(endpoints, access_token)
    except oidc.OIDCError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))

    # Noiseport does not always release an email; fall back to a stable placeholder under a
    # Noisebridge-controlled name (.invalid is rejected by the email validator).
    email = identity.email or f"{OAUTH_NAME}-{identity.sub}@sso.noisebins.noisebridge.net"
    try:
        user = await user_manager.oauth_callback(
            OAUTH_NAME,
            access_token="",  # provider tokens are not needed after sign-in, so they are not stored
            account_id=identity.sub,
            account_email=email,
            request=request,
            # Only merge into an existing email/password account when the provider vouches for the email.
            associate_by_email=identity.email_verified,
            is_verified_by_default=identity.email_verified,
        )
    except exceptions.UserAlreadyExists:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A noisebins account already uses {email}. Sign in with your password, or verify that email in {name}.",
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This noisebins account is disabled.")
    if identity.name and user.display_name != identity.name:
        user = await user_manager.user_db.update(user, {"display_name": identity.name})

    login_response = await cookie_backend.login(get_jwt_strategy(), user)
    response = RedirectResponse(flow.get("next") or "/", status_code=status.HTTP_303_SEE_OTHER)
    for cookie in login_response.headers.getlist("set-cookie"):
        response.headers.append("set-cookie", cookie)
    response.delete_cookie(STATE_COOKIE, path=router.prefix)
    return response


@session_router.post("/logout")
async def logout():
    """End the noisebins browser session. The Noiseport session itself is left alone."""
    settings = get_settings()
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response
