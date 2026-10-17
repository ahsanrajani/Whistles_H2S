"""youtube_owned_videos + x_owned_posts -- the channel's own recent posts,
with real engagement counts where the platform exposes them."""
import json
import unittest
from unittest.mock import patch

from core import collector, sources  # noqa: F401 -- import order, see test_web_backfill.py
from integrations.adapters import XOwnedPosts, YouTubeOwnedVideos


class YouTubeOwnedVideosTests(unittest.TestCase):
    def _adapter(self, logs=None):
        if logs is None:
            logs = []
        return YouTubeOwnedVideos(
            {"YOUTUBE_API_KEY": "yk", "YOUTUBE_CHANNEL_ID": "UC123"},
            logs.append, lambda *_a, **_k: None)

    def test_the_call_chain_yields_the_video_plus_its_comments_and_replies(self):
        channels = json.dumps({"items": [
            {"contentDetails": {"relatedPlaylists": {"uploads": "UU123"}}}]})
        playlist = json.dumps({"items": [
            {"snippet": {"resourceId": {"videoId": "v1"}, "title": "Market update",
                        "description": "d", "publishedAt": "2026-09-01T00:00:00Z",
                        "channelTitle": "Chase Securities",
                        "thumbnails": {"high": {"url": "https://i.ytimg.com/vi/v1/hq.jpg"}}}}]})
        stats = json.dumps({"items": [
            {"id": "v1", "statistics": {"viewCount": "100", "likeCount": "10",
                                        "commentCount": "2"}}]})
        comments = json.dumps({"items": [
            {"snippet": {"topLevelComment": {"id": "c1", "snippet": {
                "textDisplay": "Why is support so slow?",
                "authorDisplayName": "A Customer", "publishedAt": "2026-09-02T00:00:00Z"}}},
             "replies": {"comments": [
                 {"id": "r1", "snippet": {"textDisplay": "DM us your reference number",
                                          "authorDisplayName": "Chase Securities Pakistan",
                                          "publishedAt": "2026-09-02T01:00:00Z"}}]}},
        ]})
        calls = iter([channels, playlist, stats, comments])
        with patch.object(collector, "_get", side_effect=lambda *a, **k: next(calls)):
            out = list(self._adapter().fetch([]))
        self.assertEqual(len(out), 3)
        post = next(o for o in out if o["raw"]["kind"] == "post")
        self.assertEqual(post["external_id"], "video:v1")
        self.assertEqual(post["url"], "https://youtube.com/watch?v=v1")
        self.assertEqual(post["raw"]["metrics"], {"views": 100, "likes": 10, "comments": 2})
        self.assertEqual(post["raw"]["media"],
                         {"type": "youtube", "video_id": "v1",
                          "image": "https://i.ytimg.com/vi/v1/hq.jpg"})

        comment = next(o for o in out if o["raw"]["kind"] == "comment")
        self.assertEqual(comment["external_id"], "comment:c1")
        self.assertEqual(comment["raw"]["parent_id"], "video:v1")
        self.assertEqual(comment["body"], "Why is support so slow?")

        reply = next(o for o in out if o["raw"]["kind"] == "reply")
        self.assertEqual(reply["external_id"], "comment:r1")
        self.assertEqual(reply["raw"]["parent_id"], "comment:c1")

    def test_no_uploads_playlist_yields_nothing(self):
        logs = []
        with patch.object(collector, "_get", return_value=json.dumps({"items": []})):
            out = list(self._adapter(logs).fetch([]))
        self.assertEqual(out, [])
        self.assertTrue(any("no uploads playlist" in ln for ln in logs))

    def test_channel_lookup_failure_yields_nothing(self):
        logs = []
        with patch.object(collector, "_get", side_effect=RuntimeError("timeout")):
            out = list(self._adapter(logs).fetch([]))
        self.assertEqual(out, [])
        self.assertTrue(any("failed" in ln for ln in logs))


class XOwnedPostsTests(unittest.TestCase):
    def _adapter(self, logs=None):
        if logs is None:
            logs = []
        return XOwnedPosts(
            {"X_BEARER_TOKEN": "xt", "X_OWNED_HANDLE": "@ChaseSecPK"},
            logs.append, lambda *_a, **_k: None)

    def test_yields_owned_tweets_with_public_metrics(self):
        who = json.dumps({"data": {"id": "u1"}})
        tweets = json.dumps({"data": [
            {"id": "t1", "text": "KSE-100 closed up today.",
             "created_at": "2026-09-01T00:00:00Z",
             "public_metrics": {"like_count": 5, "retweet_count": 1,
                                "reply_count": 0, "quote_count": 0}}]})
        calls = iter([who, tweets])
        with patch.object(collector, "_get", side_effect=lambda *a, **k: next(calls)):
            out = list(self._adapter().fetch([]))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["url"], "https://x.com/ChaseSecPK/status/t1")
        self.assertEqual(out[0]["raw"]["metrics"],
                         {"likes": 5, "reposts": 1, "replies": 0, "quotes": 0})

    def test_unknown_handle_yields_nothing(self):
        logs = []
        with patch.object(collector, "_get", return_value=json.dumps({})):
            out = list(self._adapter(logs).fetch([]))
        self.assertEqual(out, [])
        self.assertTrue(any("not found" in ln for ln in logs))


if __name__ == "__main__":
    unittest.main()
