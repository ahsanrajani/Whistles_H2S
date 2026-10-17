"""Mint a short-lived Google OAuth2 access token from a stored refresh token.

Google access tokens expire in about an hour; a refresh token does not, so it
is what gets persisted (``GOOGLE_OAUTH2_REFRESH_TOKEN`` + the OAuth client
id/secret that issued it). Used by the Business Profile review-reply and
YouTube comment-reply write transports when no static
``GOOGLE_BUSINESS_TOKEN`` / ``YOUTUBE_OAUTH_TOKEN`` override is configured.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://oauth2.googleapis.com/token"
_TIMEOUT = 15

OAUTH_KEYS = ("GOOGLE_OAUTH2_CLIENT_ID", "GOOGLE_OAUTH2_CLIENT_SECRET",
              "GOOGLE_OAUTH2_REFRESH_TOKEN")


class OAuthError(Exception):
    pass


def has_refresh_creds(keys: dict) -> bool:
    return all(keys.get(k) for k in OAUTH_KEYS)


def mint_access_token(keys: dict) -> str:
    """One round-trip to trade the refresh token for a fresh access token."""
    if not has_refresh_creds(keys):
        raise OAuthError("missing GOOGLE_OAUTH2_CLIENT_ID/SECRET/REFRESH_TOKEN")
    data = urllib.parse.urlencode({
        "client_id": keys["GOOGLE_OAUTH2_CLIENT_ID"],
        "client_secret": keys["GOOGLE_OAUTH2_CLIENT_SECRET"],
        "refresh_token": keys["GOOGLE_OAUTH2_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST",
                                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            msg = json.loads(detail).get("error_description") or json.loads(detail).get("error")
        except ValueError:
            msg = detail[:300]
        raise OAuthError(f"token refresh failed — {exc.code}: {msg}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OAuthError(f"token refresh failed — {exc}") from exc

    token = json.loads(raw).get("access_token")
    if not token:
        raise OAuthError("token refresh response had no access_token")
    return token
