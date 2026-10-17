"""A Flask-test-client-shaped adapter over Starlette's ASGI ``TestClient``.

P1.10 migrates routers Flask → FastAPI behind the ``asgi.app`` shell (FastAPI
outer, Flask mounted as the fallback). The suite must hit whichever framework
currently owns a path, so every ``ApiTestCase`` drives ``asgi.app`` through
this adapter. It reproduces exactly the surface the tests use — ``get`` /
``post`` / ``patch``, cookie persistence, ``session_transaction()``, and
responses with ``.status_code`` / ``.headers`` / ``.get_json()`` /
``.get_data()`` — so test bodies did not change when the client flipped.
"""
from contextlib import contextmanager

import websession


class _Resp:
    """httpx Response wrapped to look like a Werkzeug/Flask test response."""

    __slots__ = ("_r",)

    def __init__(self, r):
        self._r = r

    @property
    def status_code(self):
        return self._r.status_code

    @property
    def headers(self):
        # httpx.Headers: case-insensitive, supports [key] and .get(key, default)
        return self._r.headers

    @property
    def text(self):
        return self._r.text

    @property
    def content(self):
        return self._r.content

    @property
    def data(self):
        return self._r.content

    def get_json(self, silent=False):
        try:
            return self._r.json()
        except ValueError:
            if silent:
                return None
            raise

    def get_data(self, as_text=False):
        return self._r.text if as_text else self._r.content


class AsgiTestClient:
    """Drop-in for ``flask.testing.FlaskClient`` covering what the suite uses."""

    def __init__(self, app=None):
        from starlette.testclient import TestClient

        if app is None:
            from asgi import app as app  # noqa: PLW0127

        self._c = TestClient(app, follow_redirects=False, raise_server_exceptions=True)

    # --- HTTP verbs ----------------------------------------------------
    def _request(self, method, path, *, json=None, data=None, headers=None,
                 query_string=None, files=None, **_ignored):
        resp = _Resp(self._c.request(method, path, json=json, data=data,
                                     headers=headers, params=query_string, files=files))
        # A logout (cookie delete) followed by a fresh login can leave the
        # httpx jar holding two `session` cookies under slightly different
        # domain/path keys, which makes `.cookies.get("session")` raise
        # CookieConflict. Werkzeug's own test client collapses them; do the
        # same so the server always receives one clean session cookie.
        self._collapse_session_cookie()
        return resp

    def _collapse_session_cookie(self):
        jar = self._c.cookies.jar
        matches = [c for c in jar if c.name == websession.COOKIE_NAME]
        if len(matches) <= 1:
            return
        best = next((c for c in reversed(matches) if c.value), matches[-1])
        for cookie in matches:
            if cookie is not best:
                jar.clear(cookie.domain, cookie.path, cookie.name)

    def _current_sid(self):
        values = [c.value for c in self._c.cookies.jar
                  if c.name == websession.COOKIE_NAME and c.value]
        return values[-1] if values else None

    def get(self, path, **kw):
        return self._request("GET", path, **kw)

    def post(self, path, **kw):
        return self._request("POST", path, **kw)

    def put(self, path, **kw):
        return self._request("PUT", path, **kw)

    def patch(self, path, **kw):
        return self._request("PATCH", path, **kw)

    def delete(self, path, **kw):
        return self._request("DELETE", path, **kw)

    # --- cookies / session -------------------------------------------
    @property
    def cookies(self):
        return self._c.cookies

    @contextmanager
    def session_transaction(self):
        """Read the server-side session for the client's current cookie. The
        suite only ever *reads* it (csrf_token, ws_id, perms) after a real login
        POST has established the session, so — unlike Flask's test client — this
        does not synthesise a session or write the cookie jar (doing so with a
        mismatched domain silently breaks later requests). Mutations to an
        existing session are still persisted on exit."""
        sid = self._current_sid()
        data = dict(websession.store().load(sid)) if sid else {}
        yield data
        if sid:
            websession.store().save(sid, data)


def asgi_client(app=None):
    """A fresh adapter with its own cookie jar (for tests that need a second,
    independent session — e.g. a viewer alongside an admin)."""
    return AsgiTestClient(app)
