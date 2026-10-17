"""F0.4 — realtime hub + the /api/v1/ws WebSocket."""
import unittest

from core import realtime

from ._db import ApiTestCase


class HubTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_reaches_only_matching_subscribers(self):
        hub = realtime.Hub()
        cid_a, qa = hub.register()
        cid_b, qb = hub.register()
        hub.set_topics(cid_a, ["case:1", "queue:7"])
        hub.set_topics(cid_b, ["case:2"])

        reached = hub.publish("case:1", {"hello": "world"})
        self.assertEqual(reached, 1)
        frame = qa.get_nowait()
        self.assertEqual(frame["topic"], "case:1")
        self.assertEqual(frame["data"], {"hello": "world"})
        self.assertTrue(qb.empty())

        hub.unregister(cid_a)
        self.assertEqual(hub.publish("case:1", {}), 0)
        self.assertEqual(hub.connection_count(), 1)


class RealtimeWsTests(ApiTestCase):
    def _login(self, user="admin", pw="admin123"):
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login", json={"username": user, "password": pw},
                         headers={"X-CSRF-Token": token})

    def test_unauthenticated_socket_is_closed(self):
        from starlette.websockets import WebSocketDisconnect
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client._c.websocket_connect("/api/v1/ws"):
                pass
        self.assertEqual(caught.exception.code, 4401)

    def test_subscribe_then_receive_a_published_frame(self):
        self._login()
        with self.client._c.websocket_connect("/api/v1/ws") as sock:
            self.assertEqual(sock.receive_json()["type"], "ready")
            sock.send_json({"type": "subscribe", "topics": ["case:5", "queue:999"]})
            # ping/pong is processed after subscribe on the same receive loop,
            # so a pong back means the subscribe has landed.
            sock.send_json({"type": "ping"})
            self.assertEqual(sock.receive_json()["type"], "pong")

            realtime.publish("case:5", {"kind": "assigned", "assignee_id": 3})
            frame = sock.receive_json()
            self.assertEqual(frame["topic"], "case:5")
            self.assertEqual(frame["data"]["kind"], "assigned")

    def test_cannot_subscribe_to_another_workspaces_queue(self):
        self._login()
        with self.client._c.websocket_connect("/api/v1/ws") as sock:
            sock.receive_json()
            sock.send_json({"type": "subscribe", "topics": ["queue:424242", "case:9"]})
            sock.send_json({"type": "ping"})
            self.assertEqual(sock.receive_json()["type"], "pong")
            # a frame on the disallowed topic must not arrive
            realtime.publish("queue:424242", {"nope": True})
            realtime.publish("case:9", {"ok": True})
            frame = sock.receive_json()
            self.assertEqual(frame["topic"], "case:9")


if __name__ == "__main__":
    unittest.main()
