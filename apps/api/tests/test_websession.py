"""P1.10b — the framework-neutral session store.

It must round-trip a dict, read what Flask-Session writes (same client, same
msgpack), and — the point of it — see a session that a Flask login just
created, so a ported FastAPI route continues the same session.
"""
import unittest

import msgspec

import app as flask_module
import websession

from ._db import ApiTestCase


class SessionStoreUnitTests(unittest.TestCase):
    def setUp(self):
        import fakeredis
        self.client = fakeredis.FakeStrictRedis()
        self.store = websession.SessionStore(self.client)

    def test_round_trips_a_dict(self):
        self.store.save("sid1", {"user_id": 7, "perms": ["care:view"]})
        self.assertEqual(self.store.load("sid1"),
                         {"user_id": 7, "perms": ["care:view"]})

    def test_missing_or_garbage_reads_as_empty(self):
        self.assertEqual(self.store.load("nope"), {})
        self.assertEqual(self.store.load(""), {})
        self.client.set("guru:sess:bad", b"\xff\xff not msgpack \x00")
        self.assertEqual(self.store.load("bad"), {})

    def test_delete_removes_the_key(self):
        self.store.save("sid2", {"a": 1})
        self.store.delete("sid2")
        self.assertEqual(self.store.load("sid2"), {})

    def test_reads_a_flask_session_style_blob(self):
        blob = msgspec.msgpack.Encoder().encode({"user_id": 3, "role": "admin"})
        self.client.set("guru:sess:fs", blob, ex=600)
        self.assertEqual(self.store.load("fs"), {"user_id": 3, "role": "admin"})

    def test_writes_a_ttl(self):
        self.store.save("sid3", {"x": 1})
        self.assertGreater(self.client.ttl("guru:sess:sid3"), 0)


class SharedWithFlaskSessionTests(ApiTestCase):
    def test_store_sees_the_session_a_login_created(self):
        # login is FastAPI-native (P1.10) and writes via deps.establish_session;
        # the websession store must see it under the cookie's sid.
        csrf = self.client.get("/api/v1/csrf").get_json()["token"]
        resp = self.client.post("/api/v1/auth/login",
                                json={"username": "admin", "password": "admin123"},
                                headers={"X-CSRF-Token": csrf})
        self.assertEqual(resp.status_code, 200)

        sid = self.client.cookies.get("session")
        data = websession.store().load(sid)
        self.assertEqual(data["role"], "admin")
        self.assertIn("perms", data)
        self.assertTrue(data["perms"])

    def test_store_and_flask_session_share_one_client(self):
        self.assertIs(websession.store()._client,
                      flask_module.app.config["SESSION_REDIS"])


if __name__ == "__main__":
    unittest.main()
