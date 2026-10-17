"""Server-side session store shared by the Flask app and the ported FastAPI
routes during the P1.10 migration. One Redis client, one wire format."""
from .store import COOKIE_NAME, KEY_PREFIX, SessionStore, new_sid

_store: SessionStore | None = None


def configure(redis_client, **kwargs) -> SessionStore:
    """Bind the process-wide store to the one Redis client. Called by app.py."""
    global _store
    _store = SessionStore(redis_client, **kwargs)
    return _store


def store() -> SessionStore:
    if _store is None:
        raise RuntimeError("websession.configure() has not been called")
    return _store


__all__ = ["SessionStore", "configure", "store", "new_sid", "COOKIE_NAME", "KEY_PREFIX"]
