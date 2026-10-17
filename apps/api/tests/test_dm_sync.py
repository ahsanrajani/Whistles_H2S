"""core/dm_sync.py -- Facebook Messenger / Instagram DM ingestion straight
into Care. Every Graph API call mocked; nothing hits the network."""
import json
import unittest
from unittest.mock import patch

import sqlalchemy as sa

from core import collector, dm_sync

from ._db import DbTestCase

PAGE_ID = "105737368397802"
IG_USER_ID = "17841464207856659"
KEYS = {"META_ACCESS_TOKEN": "user-token", "META_PAGE_ID": PAGE_ID}
KEYS_WITH_IG = {**KEYS, "META_IG_USER_ID": IG_USER_ID}

ACCOUNTS_OK = json.dumps({"data": [
    {"id": PAGE_ID, "access_token": "page-token"},
]})
MESSENGER_CONVS = json.dumps({"data": [
    {"id": "t_1", "participants": {"data": [
        {"id": "999", "name": "Ghulam Mustafa"}, {"id": PAGE_ID, "name": "Chase Securities"},
    ]}},
]})
MESSENGER_MSGS = json.dumps({"data": [
    {"id": "m_1", "from": {"id": "999"}, "message": "Any update on my request?",
     "created_time": "2026-09-08T05:11:39+0000"},
]})
# Root-caused 2026-09-11 (hamzaraza / C-117): Instagram's conversations API
# represents Chase's own side by the IG Business Account id, not page_id --
# both participants are "not page_id", so a page_id-only exclusion filter
# picked whichever sorted first. Here that's deliberately Chase's own
# account (id_first_in_list), matching the real bug -- a correct fix must
# still land on the real customer (271...).
INSTAGRAM_CONVS = json.dumps({"data": [
    {"id": "ig_t_1", "participants": {"data": [
        {"username": "chasesecuritiespak", "id": IG_USER_ID},
        {"username": "hamzaraza._", "id": "27663306926680924"},
    ]}},
]})
INSTAGRAM_MSGS_INBOUND = json.dumps({"data": [
    {"id": "ig_m_1", "from": {"id": "27663306926680924"}, "message": "hi",
     "created_time": "2026-09-11T17:49:40+0000"},
]})
INSTAGRAM_MSGS_OUTBOUND = json.dumps({"data": [
    {"id": "ig_m_2", "from": {"id": IG_USER_ID}, "message": "Hello! How can we help?",
     "created_time": "2026-09-11T17:50:48+0000"},
]})
EMPTY_CONVS = json.dumps({"data": []})


def _fake_get(urls_by_kind):
    def _get(url, timeout=30):  # noqa: ARG001 -- matches collector._get's signature
        if "me/accounts" in url:
            return urls_by_kind["accounts"]
        if "platform=messenger" in url:
            return urls_by_kind.get("messenger_convs", EMPTY_CONVS)
        if "platform=instagram" in url:
            return urls_by_kind.get("instagram_convs", EMPTY_CONVS)
        if "/t_1/messages" in url:
            return urls_by_kind.get("messenger_msgs", EMPTY_CONVS)
        if "/ig_t_1/messages" in url:
            return urls_by_kind.get("instagram_msgs", EMPTY_CONVS)
        return EMPTY_CONVS
    return _get


class DmSyncTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def test_no_meta_creds_raises(self):
        with self.assertRaises(RuntimeError):
            dm_sync.sync(self.s, 1, {})

    def test_a_real_inbound_dm_is_ingested_as_a_care_case(self):
        with patch.object(collector, "_get", side_effect=_fake_get({
                "accounts": ACCOUNTS_OK, "messenger_convs": MESSENGER_CONVS,
                "messenger_msgs": MESSENGER_MSGS})):
            out = dm_sync.sync(self.s, 1, KEYS)
        self.db.commit()
        self.assertEqual(out["messenger"]["ingested"], 1)
        self.assertEqual(out["instagram"]["ingested"], 0)

        row = self.s.execute(sa.text(
            "SELECT direction, channel, body, platform_ref FROM case_message "
            "WHERE workspace_id = 1")).mappings().one()
        self.assertEqual(row["direction"], "inbound")
        self.assertEqual(row["channel"], "messenger")
        self.assertEqual(row["body"], "Any update on my request?")
        self.assertEqual(row["platform_ref"], "m_1")

    def test_a_second_sync_does_not_duplicate_the_same_message(self):
        get = _fake_get({"accounts": ACCOUNTS_OK, "messenger_convs": MESSENGER_CONVS,
                         "messenger_msgs": MESSENGER_MSGS})
        with patch.object(collector, "_get", side_effect=get):
            dm_sync.sync(self.s, 1, KEYS)
            self.db.commit()
            out2 = dm_sync.sync(self.s, 1, KEYS)
        self.db.commit()
        self.assertEqual(out2["messenger"]["ingested"], 0)
        count = self.s.execute(sa.text(
            "SELECT count(*) FROM case_message WHERE workspace_id = 1")).scalar()
        self.assertEqual(count, 1)

    def test_an_outbound_message_already_sent_natively_is_recorded_too(self):
        outbound_msgs = json.dumps({"data": [
            {"id": "m_2", "from": {"id": PAGE_ID}, "message": "Sure, one moment.",
             "created_time": "2026-09-08T05:15:00+0000"},
        ]})
        with patch.object(collector, "_get", side_effect=_fake_get({
                "accounts": ACCOUNTS_OK, "messenger_convs": MESSENGER_CONVS,
                "messenger_msgs": outbound_msgs})):
            dm_sync.sync(self.s, 1, KEYS)
        self.db.commit()
        row = self.s.execute(sa.text(
            "SELECT direction FROM case_message WHERE workspace_id = 1")).mappings().one()
        self.assertEqual(row["direction"], "outbound")

    def test_a_failed_platform_does_not_block_the_other(self):
        def boom_on_instagram(url, timeout=30):
            if "platform=instagram" in url:
                raise RuntimeError("rate limited")
            return _fake_get({"accounts": ACCOUNTS_OK, "messenger_convs": MESSENGER_CONVS,
                              "messenger_msgs": MESSENGER_MSGS})(url)
        with patch.object(collector, "_get", side_effect=boom_on_instagram):
            out = dm_sync.sync(self.s, 1, KEYS_WITH_IG)
        self.db.commit()
        self.assertEqual(out["messenger"]["ingested"], 1)
        self.assertIn("rate limited", out["instagram"]["error"])

    def test_no_page_token_for_the_configured_page_id_raises(self):
        with patch.object(collector, "_get",
                          return_value=json.dumps({"data": [{"id": "other-page",
                                                              "access_token": "x"}]})):
            with self.assertRaises(RuntimeError):
                dm_sync.sync(self.s, 1, KEYS)

    def test_instagram_is_skipped_cleanly_with_no_ig_user_id_configured(self):
        # KEYS (no META_IG_USER_ID) -- Instagram DMs need it and Messenger
        # doesn't, so this must be a clean per-platform skip, not a crash.
        with patch.object(collector, "_get", side_effect=_fake_get({
                "accounts": ACCOUNTS_OK, "messenger_convs": MESSENGER_CONVS,
                "messenger_msgs": MESSENGER_MSGS})):
            out = dm_sync.sync(self.s, 1, KEYS)
        self.db.commit()
        self.assertEqual(out["messenger"]["ingested"], 1)
        self.assertEqual(out["instagram"]["ingested"], 0)
        self.assertIn("META_IG_USER_ID", out["instagram"]["error"])

    # --- Instagram business-id bug (hamzaraza / C-117, 2026-09-11) --------
    def test_instagram_inbound_dm_resolves_the_real_customer_not_chases_own_account(self):
        with patch.object(collector, "_get", side_effect=_fake_get({
                "accounts": ACCOUNTS_OK, "instagram_convs": INSTAGRAM_CONVS,
                "instagram_msgs": INSTAGRAM_MSGS_INBOUND})):
            out = dm_sync.sync(self.s, 1, KEYS_WITH_IG)
        self.db.commit()
        self.assertEqual(out["instagram"]["ingested"], 1)
        row = self.s.execute(sa.text(
            "SELECT direction, body FROM case_message WHERE workspace_id = 1")).mappings().one()
        self.assertEqual(row["direction"], "inbound")
        self.assertEqual(row["body"], "hi")
        customer = self.s.execute(sa.text(
            "SELECT handle FROM customer WHERE workspace_id = 1")).mappings().one()
        # the real sender, never Chase's own IG_USER_ID
        self.assertEqual(customer["handle"], "27663306926680924")

    def test_instagram_outbound_reply_is_recorded_as_outbound_not_inbound(self):
        with patch.object(collector, "_get", side_effect=_fake_get({
                "accounts": ACCOUNTS_OK, "instagram_convs": INSTAGRAM_CONVS,
                "instagram_msgs": INSTAGRAM_MSGS_OUTBOUND})):
            out = dm_sync.sync(self.s, 1, KEYS_WITH_IG)
        self.db.commit()
        self.assertEqual(out["instagram"]["ingested"], 1)
        row = self.s.execute(sa.text(
            "SELECT direction FROM case_message WHERE workspace_id = 1")).mappings().one()
        self.assertEqual(row["direction"], "outbound")

    # --- Instagram-Login route (2026-09-16, standalone app + native token) --
    def test_instagram_login_route_hits_graph_instagram_com_directly(self):
        """When INSTAGRAM_LOGIN_ACCESS_TOKEN is configured, Instagram must go
        through graph.instagram.com on its own token -- never through the
        Facebook-Login /platform=instagram call (the persistent-500 route)."""
        keys = {**KEYS_WITH_IG, "INSTAGRAM_LOGIN_ACCESS_TOKEN": "ig-login-tok"}
        seen_urls = []

        def fake(url, timeout=30):
            seen_urls.append(url)
            if "me/accounts" in url:
                return ACCOUNTS_OK
            if "messenger" in url and "graph.facebook.com" in url:
                return MESSENGER_CONVS if "/conversations" in url else MESSENGER_MSGS
            if url.startswith(dm_sync.IG_GRAPH):
                if "/conversations" in url:
                    return INSTAGRAM_CONVS
                return INSTAGRAM_MSGS_INBOUND
            return EMPTY_CONVS

        with patch.object(collector, "_get", side_effect=fake):
            out = dm_sync.sync(self.s, 1, keys)
        self.db.commit()
        self.assertEqual(out["instagram"]["ingested"], 1)
        ig_urls = [u for u in seen_urls if u.startswith(dm_sync.IG_GRAPH)]
        self.assertTrue(ig_urls, "expected at least one graph.instagram.com call")
        self.assertTrue(all("access_token=ig-login-tok" in u for u in ig_urls))
        self.assertTrue(all("platform=" not in u for u in ig_urls))
        self.assertFalse(any("platform=instagram" in u for u in seen_urls))

    def test_instagram_login_route_survives_a_broken_facebook_page_token(self):
        """The whole point of the standalone route: Instagram DMs must keep
        working even when the shared Facebook Page token can't be resolved
        (e.g. Meta's app-level rate limit on that token)."""
        keys = {**KEYS_WITH_IG, "INSTAGRAM_LOGIN_ACCESS_TOKEN": "ig-login-tok"}

        def fake(url, timeout=30):
            if "me/accounts" in url:
                raise RuntimeError("(#4) Application request limit reached")
            if url.startswith(dm_sync.IG_GRAPH):
                return INSTAGRAM_CONVS if "/conversations" in url else INSTAGRAM_MSGS_INBOUND
            return EMPTY_CONVS

        with patch.object(collector, "_get", side_effect=fake):
            out = dm_sync.sync(self.s, 1, keys)
        self.db.commit()
        self.assertIn("error", out["messenger"])
        self.assertEqual(out["instagram"]["ingested"], 1)

    def test_no_ig_login_token_falls_back_to_facebook_login_route(self):
        """Unchanged behaviour for workspaces without the new credential."""
        with patch.object(collector, "_get", side_effect=_fake_get({
                "accounts": ACCOUNTS_OK, "instagram_convs": INSTAGRAM_CONVS,
                "instagram_msgs": INSTAGRAM_MSGS_INBOUND})):
            out = dm_sync.sync(self.s, 1, KEYS_WITH_IG)
        self.db.commit()
        self.assertEqual(out["instagram"]["ingested"], 1)


if __name__ == "__main__":
    unittest.main()
