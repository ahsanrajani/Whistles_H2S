"""Per-workspace feature flags — registry, resolution, RLS, admin API."""
import unittest

import sqlalchemy as sa

from core import features
from db.repositories import feature_flags

from ._db import ApiTestCase, DbTestCase


class RegistryTests(unittest.TestCase):
    def test_catalog_covers_every_key_with_a_kind_and_label(self):
        cat = features.catalog()
        self.assertEqual([c["key"] for c in cat], list(features.KEYS))
        self.assertTrue(all(c["kind"] in ("surface", "module", "cap") for c in cat))
        self.assertTrue(all(c["label"] for c in cat))

    def test_known_keys_span_the_three_kinds(self):
        self.assertIn("surface.scam", features.KEYS)
        self.assertIn("module.care", features.KEYS)
        self.assertIn("cap.ai_assist", features.KEYS)

    def test_is_valid(self):
        self.assertTrue(features.is_valid("cap.export"))
        self.assertFalse(features.is_valid("cap.nonsense"))


class ResolveTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def test_everything_on_by_default(self):
        resolved = features.resolve(self.s, 1)
        self.assertEqual(set(resolved), set(features.KEYS))
        self.assertTrue(all(resolved.values()))
        self.assertTrue(features.enabled(self.s, 1, "surface.triage"))

    def test_a_row_turns_one_key_off_and_leaves_the_rest(self):
        feature_flags.set_enabled(self.s, 1, "surface.scam", False)
        self.db.commit()
        resolved = features.resolve(self.s, 1)
        self.assertFalse(resolved["surface.scam"])
        self.assertFalse(features.enabled(self.s, 1, "surface.scam"))
        self.assertTrue(resolved["surface.triage"])
        self.assertTrue(resolved["module.care"])

    def test_re_enabling_clears_it(self):
        feature_flags.set_enabled(self.s, 1, "module.reporting", False)
        self.db.commit()
        self.assertFalse(features.enabled(self.s, 1, "module.reporting"))
        feature_flags.set_enabled(self.s, 1, "module.reporting", True)
        self.db.commit()
        self.assertTrue(features.enabled(self.s, 1, "module.reporting"))

    def test_unknown_key_is_treated_as_on(self):
        self.assertTrue(features.enabled(self.s, 1, "cap.does-not-exist"))


class RlsTests(DbTestCase):
    def test_a_workspace_only_sees_its_own_flags(self):
        for wid in (1, 2):
            self.db.session.execute(sa.text(
                "INSERT INTO workspace(id,name,market,created_at) "
                "VALUES (:i,:n,'PK','now')"), {"i": wid, "n": f"WS{wid}"})
        self.db.commit()
        feature_flags.set_enabled(self.db.session, 1, "surface.scam", False)
        feature_flags.set_enabled(self.db.session, 2, "surface.triage", False)
        self.db.commit()
        self.assertFalse(features.enabled(self.db.session, 1, "surface.scam"))
        self.assertTrue(features.enabled(self.db.session, 1, "surface.triage"))
        self.assertTrue(features.enabled(self.db.session, 2, "surface.scam"))


class AdminApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _put(self, key, enabled):
        return self.client.put(f"/api/v1/admin/features/{key}",
                               json={"enabled": enabled},
                               headers={"X-CSRF-Token": self.csrf})

    def test_list_toggle_and_reflect_in_auth_me(self):
        listing = self.client.get("/api/v1/admin/features").get_json()["features"]
        self.assertEqual(len(listing), len(features.KEYS))
        self.assertTrue(all(f["enabled"] for f in listing))

        self.assertEqual(self._put("module.content", False).status_code, 200)

        listing = self.client.get("/api/v1/admin/features").get_json()["features"]
        self.assertFalse(next(f for f in listing if f["key"] == "module.content")["enabled"])
        self.assertTrue(next(f for f in listing if f["key"] == "module.care")["enabled"])

        me = self.client.get("/api/v1/auth/me").get_json()["user"]
        self.assertFalse(me["features"]["module.content"])
        self.assertTrue(me["features"]["surface.overview"])

    def test_unknown_feature_is_404(self):
        self.assertEqual(self._put("cap.imaginary", False).status_code, 404)

    def test_a_disabled_capability_403s_its_route(self):
        # export is on by default
        self.assertEqual(
            self.client.get("/api/v1/mentions/export.csv").status_code, 200)
        self.assertEqual(self._put("cap.export", False).status_code, 200)
        r = self.client.get("/api/v1/mentions/export.csv")
        self.assertEqual(r.status_code, 403)
        self.assertIn("cap.export", r.get_json().get("error", ""))
        # re-enable and it works again
        self._put("cap.export", True)
        self.assertEqual(
            self.client.get("/api/v1/mentions/export.csv").status_code, 200)

    def test_disabling_alerts_dispatch_blocks_the_route(self):
        self._put("cap.alerts_dispatch", False)
        self.assertEqual(
            self.client.post("/api/v1/alerts/dispatch",
                             headers={"X-CSRF-Token": self.csrf}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
