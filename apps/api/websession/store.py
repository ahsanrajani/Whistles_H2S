"""Framework-neutral server-side sessions on Redis.

The wire format matches Flask-Session 0.8 — msgpack of a plain dict, stored at
``<prefix><sid>`` with a TTL, the opaque ``secrets.token_urlsafe`` sid carried
in a cookie named ``session`` — so a session opened on a still-Flask route and
one continued on a ported FastAPI route are the *same* session. Flask keeps its
own ``RedisSessionInterface`` through the P1.10 migration; this store is the
ASGI side of the same coin and shares the one Redis client (see
``websession.configure``).
"""
import secrets
from datetime import timedelta

import msgspec

COOKIE_NAME = "session"
KEY_PREFIX = "guru:sess:"
SID_BYTES = 32
DEFAULT_TTL = timedelta(days=7)

_encoder = msgspec.msgpack.Encoder()
_decoder = msgspec.msgpack.Decoder()
_json_decoder = msgspec.json.Decoder()


def new_sid() -> str:
    return secrets.token_urlsafe(SID_BYTES)


def _decode(blob: bytes) -> dict:
    # msgpack is what we and Flask-Session write; json is the documented
    # Flask-Session alternate. A corrupt blob is treated as no session.
    for decoder in (_decoder, _json_decoder):
        try:
            value = decoder.decode(blob)
            return value if isinstance(value, dict) else {}
        except msgspec.DecodeError:
            continue
    return {}


class SessionStore:
    def __init__(self, client, *, key_prefix: str = KEY_PREFIX, ttl=DEFAULT_TTL):
        self._client = client
        self._prefix = key_prefix
        self._ttl = int(ttl.total_seconds()) if isinstance(ttl, timedelta) else int(ttl)

    def _key(self, sid: str) -> str:
        return self._prefix + sid

    def load(self, sid: str) -> dict:
        if not sid:
            return {}
        blob = self._client.get(self._key(sid))
        return _decode(blob) if blob else {}

    def save(self, sid: str, data: dict) -> None:
        self._client.set(self._key(sid), _encoder.encode(dict(data)), ex=self._ttl)

    def delete(self, sid: str) -> None:
        self._client.delete(self._key(sid))
