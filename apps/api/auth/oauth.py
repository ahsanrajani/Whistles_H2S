"""Google "Sign in with Google", plus the account-linking rule.

``register(app)`` wires an Authlib client if ``GOOGLE_OAUTH_CLIENT_ID`` /
``GOOGLE_OAUTH_CLIENT_SECRET`` are set. With no credentials the provider runs in
**mock mode** — ``start`` bounces straight to ``callback`` carrying an email —
so the flow and its tests work offline.

Linking rule (``resolve``):

1. a known ``identity(provider, subject)`` → log that user in;
2. else an active ``user`` whose ``email`` matches the verified address → create
   the link and log in;
3. else refuse. Accounts are created by an admin, never auto-provisioned from a
   bare Google login.
"""
import os

from flask import redirect, request, url_for

GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"

_oauth = None            # Authlib OAuth registry, or None in mock mode
_mock = True


class OAuthError(Exception):
    """The provider round-trip failed (bad state, denied consent, unverified)."""


class OAuthLoginError(Exception):
    """The Google identity is valid but maps to no Guru account."""


def register(app) -> None:
    global _oauth, _mock
    client_id = (os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    if not (client_id and client_secret):
        _mock = True
        app.logger.warning("GOOGLE_OAUTH_CLIENT_ID unset — Google sign-in is in mock mode.")
        return
    from authlib.integrations.flask_client import OAuth

    _oauth = OAuth(app)
    _oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=GOOGLE_DISCOVERY,
        client_kwargs={"scope": "openid email profile"},
    )
    _mock = False


def _redirect_uri() -> str:
    base = (os.environ.get("OAUTH_REDIRECT_BASE") or "").rstrip("/")
    path = url_for("api_v1.oauth_google_callback")
    return f"{base}{path}" if base else request.url_root.rstrip("/") + path


def start():
    """Return a redirect to Google's consent screen (or, in mock mode, straight
    to our own callback)."""
    if _mock:
        email = (request.args.get("as") or os.environ.get("GURU_ADMIN_EMAIL")
                 or "admin@example.com")
        return redirect(f"{url_for('api_v1.oauth_google_callback')}?mock=1&email={email}")
    return _oauth.google.authorize_redirect(_redirect_uri())


def finish() -> dict:
    """Complete the round-trip. Returns ``{"subject", "email"}`` or raises
    :class:`OAuthError`."""
    if _mock and request.args.get("mock"):
        email = (request.args.get("email") or "").strip().lower()
        if not email:
            raise OAuthError("mock callback needs an email")
        return {"subject": f"mock:{email}", "email": email}
    if _mock:
        raise OAuthError("Google sign-in is not configured")
    try:
        token = _oauth.google.authorize_access_token()
    except Exception as exc:                       # Authlib raises many shapes
        raise OAuthError(str(exc)) from exc
    info = token.get("userinfo") or {}
    if not info.get("email") or info.get("email_verified") is False:
        raise OAuthError("Google account has no verified email")
    return {"subject": str(info["sub"]), "email": info["email"].strip().lower()}


def resolve(session, *, subject, email, now):
    """Map a verified Google identity to a login row ``(id, username, role,
    workspace_id)``. Links a first-time identity to an existing account by
    email; refuses an unknown email. Caller commits."""
    from db import repositories as repo

    linked = repo.identity.by_provider_subject(session, "google", subject)
    if linked:
        repo.identity.touch_login(session, linked[0], now)
        row = repo.users.login_row(session, linked[1])
        if not row:
            raise OAuthLoginError("The linked account is disabled.")
        return row

    user = repo.users.by_email(session, email)
    if not user:
        raise OAuthLoginError(
            f"No Guru account for {email}. Ask an admin to add you.")
    repo.identity.link(session, provider="google", subject=subject,
                       user_id=user[0], email=email, created_at=now)
    return user


def is_mock() -> bool:
    return _mock


# --- ASGI / FastAPI variants (P1.10) -------------------------------------
# The Flask `start` / `finish` above read `flask.request`; these take the
# framework-neutral pieces so `api_fastapi/auth.py` can drive the same flow.
_asgi_oauth = None


def register_asgi(_app=None) -> None:
    """Build the Authlib *Starlette* client for the FastAPI auth router. Mock
    mode (no client registered) when the creds are absent — same rule as
    :func:`register`."""
    global _asgi_oauth
    client_id = (os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    if not (client_id and client_secret):
        _asgi_oauth = None
        return
    from authlib.integrations.starlette_client import OAuth

    _asgi_oauth = OAuth()
    _asgi_oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=GOOGLE_DISCOVERY,
        client_kwargs={"scope": "openid email profile"},
    )


def mock_callback_url(as_email: str | None = None) -> str:
    email = (as_email or os.environ.get("GURU_ADMIN_EMAIL") or "admin@example.com")
    return f"/api/v1/auth/oauth/google/callback?mock=1&email={email}"


def _asgi_redirect_uri(request) -> str:
    base = (os.environ.get("OAUTH_REDIRECT_BASE") or "").rstrip("/")
    path = "/api/v1/auth/oauth/google/callback"
    return f"{base}{path}" if base else str(request.base_url).rstrip("/") + path


async def start_asgi(request):
    """Return a Starlette redirect to Google's consent screen. Mock mode is
    handled by the caller (it just 302s to :func:`mock_callback_url`)."""
    if _asgi_oauth is None:
        raise OAuthError("Google sign-in is not configured")
    return await _asgi_oauth.google.authorize_redirect(
        request, _asgi_redirect_uri(request))


async def finish_asgi(request) -> dict:
    """Complete the round-trip for the FastAPI callback. ``{"subject","email"}``
    or raises :class:`OAuthError`."""
    params = request.query_params
    if _mock and params.get("mock"):
        email = (params.get("email") or "").strip().lower()
        if not email:
            raise OAuthError("mock callback needs an email")
        return {"subject": f"mock:{email}", "email": email}
    if _mock or _asgi_oauth is None:
        raise OAuthError("Google sign-in is not configured")
    try:
        token = await _asgi_oauth.google.authorize_access_token(request)
    except Exception as exc:                       # Authlib raises many shapes
        raise OAuthError(str(exc)) from exc
    info = token.get("userinfo") or {}
    if not info.get("email") or info.get("email_verified") is False:
        raise OAuthError("Google account has no verified email")
    return {"subject": str(info["sub"]), "email": info["email"].strip().lower()}
