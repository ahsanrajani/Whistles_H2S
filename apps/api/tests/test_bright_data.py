import io
import json
import unittest
import urllib.error
import urllib.parse

from core.bright_data import (
    FACEBOOK_COMMENTS_DATASET,
    FACEBOOK_PAGE_POSTS_DATASET,
    FACEBOOK_POST_DATASET,
    INSTAGRAM_COMMENTS_DATASET,
    INSTAGRAM_POSTS_DATASET,
    BrightDataClient,
    BrightDataError,
)
from scripts.probe_bright_data import quality_report


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class BrightDataClientTests(unittest.TestCase):
    def test_one_post_request_keeps_token_in_header_and_uses_one_input(self):
        seen = {}

        def open_request(request, timeout):
            seen.setdefault("request", request)
            seen["timeout"] = timeout
            if "/trigger?" in request.full_url:
                return Response(json.dumps({"snapshot_id": "snap_1"}).encode())
            if "/progress/" in request.full_url:
                return Response(json.dumps({"status": "ready"}).encode())
            return Response(json.dumps([{"post_id": "p1"}]).encode())

        result = BrightDataClient("secret-token", opener=open_request).scrape_one(
            FACEBOOK_POST_DATASET, "https://www.facebook.com/page/posts/1"
        )

        self.assertEqual(result.records, [{"post_id": "p1"}])
        self.assertNotIn("secret-token", seen["request"].full_url)
        self.assertEqual(seen["request"].headers["Authorization"], "Bearer secret-token")
        self.assertEqual(
            json.loads(seen["request"].data),
            [{"url": "https://www.facebook.com/page/posts/1"}],
        )

    def test_page_discovery_sends_one_username_and_provider_side_limits(self):
        seen = []

        def open_request(request, timeout):
            seen.append(request)
            if "/scrape?" in request.full_url:
                return Response(json.dumps({"snapshot_id": "snap_posts"}).encode())
            if "/progress/" in request.full_url:
                return Response(json.dumps({"status": "ready"}).encode())
            return Response(json.dumps([{"post_id": "p1"}]).encode())

        result = BrightDataClient("token", opener=open_request).discover_facebook_page_posts(
            "BankAlfalahOfficial", 5
        )
        trigger = seen[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(trigger.full_url).query)
        self.assertEqual(query["dataset_id"], [FACEBOOK_PAGE_POSTS_DATASET])
        self.assertEqual(query["type"], ["discover_new"])
        self.assertEqual(query["discover_by"], ["user_name"])
        self.assertEqual(query["limit_per_input"], ["5"])
        self.assertNotIn("limit_multiple_results", query)
        self.assertEqual(
            json.loads(trigger.data), {"input": [{"user_name": "BankAlfalahOfficial"}]}
        )
        self.assertEqual(result.records, [{"post_id": "p1"}])

    def test_instagram_discovery_sends_one_username_and_provider_side_limits(self):
        seen = []

        def open_request(request, timeout):
            seen.append(request)
            if "/scrape?" in request.full_url:
                return Response(json.dumps({"snapshot_id": "snap_ig"}).encode())
            if "/progress/" in request.full_url:
                return Response(json.dumps({"status": "ready"}).encode())
            return Response(json.dumps([{"post_id": "ig1"}]).encode())

        result = BrightDataClient("token", opener=open_request).discover_instagram_profile_posts(
            "bankalfalah", 5
        )
        trigger = seen[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(trigger.full_url).query)
        self.assertEqual(query["dataset_id"], [INSTAGRAM_POSTS_DATASET])
        self.assertEqual(query["type"], ["discover_new"])
        self.assertEqual(query["discover_by"], ["user_name"])
        self.assertEqual(query["limit_per_input"], ["5"])
        self.assertEqual(
            json.loads(trigger.data), {"input": [{"user_name": "bankalfalah"}]}
        )
        self.assertEqual(result.records, [{"post_id": "ig1"}])

    def test_instagram_discovery_rejects_bad_inputs_before_network(self):
        client = BrightDataClient("token", opener=lambda *_a, **_k: self.fail())
        with self.assertRaises(ValueError):
            client.discover_instagram_profile_posts("bad name!", 5)
        with self.assertRaises(ValueError):
            client.discover_instagram_profile_posts("bankalfalah", 0)

    def test_comment_collection_sends_one_input_per_post_with_a_record_cap(self):
        seen = []

        def open_request(request, timeout):
            seen.append(request)
            if "/trigger?" in request.full_url:
                return Response(json.dumps({"snapshot_id": "snap_c"}).encode())
            if "/progress/" in request.full_url:
                return Response(json.dumps({"status": "ready"}).encode())
            return Response(json.dumps([{"comment_id": "c1"}]).encode())

        urls = [
            "https://www.facebook.com/BankAlfalahOfficial/posts/1",
            "https://www.facebook.com/BankAlfalahOfficial/posts/2",
        ]
        result = BrightDataClient("token", opener=open_request).collect_facebook_post_comments(
            urls, 50
        )
        trigger = seen[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(trigger.full_url).query)
        self.assertEqual(query["dataset_id"], [FACEBOOK_COMMENTS_DATASET])
        self.assertEqual(
            json.loads(trigger.data),
            [{"url": urls[0], "limit_records": 50}, {"url": urls[1], "limit_records": 50}],
        )
        self.assertEqual(result.records, [{"comment_id": "c1"}])

    def test_comment_collection_rejects_bad_inputs_before_network(self):
        client = BrightDataClient("token", opener=lambda *_a, **_k: self.fail())
        with self.assertRaises(ValueError):
            client.collect_facebook_post_comments([], 50)
        with self.assertRaises(ValueError):
            client.collect_facebook_post_comments(
                ["https://example.com/not-facebook"], 50
            )
        with self.assertRaises(ValueError):
            client.collect_facebook_post_comments(
                ["https://www.facebook.com/x/posts/1"], 0
            )
        # the Instagram variant shares the guard but pins its own host
        with self.assertRaises(ValueError):
            client.collect_instagram_post_comments(
                ["https://www.facebook.com/x/posts/1"], 50
            )

    def test_instagram_comment_collection_targets_the_instagram_dataset(self):
        seen = []

        def open_request(request, timeout):
            seen.append(request)
            if "/trigger?" in request.full_url:
                return Response(json.dumps({"snapshot_id": "snap_igc"}).encode())
            if "/progress/" in request.full_url:
                return Response(json.dumps({"status": "ready"}).encode())
            return Response(json.dumps([{"comment_id": "igc1"}]).encode())

        url = "https://www.instagram.com/p/ABC123/"
        result = BrightDataClient("token", opener=open_request).collect_instagram_post_comments(
            [url], 25
        )
        trigger = seen[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(trigger.full_url).query)
        self.assertEqual(query["dataset_id"], [INSTAGRAM_COMMENTS_DATASET])
        self.assertEqual(json.loads(trigger.data), [{"url": url, "limit_records": 25}])
        self.assertEqual(result.records, [{"comment_id": "igc1"}])

    def test_unapproved_dataset_and_non_facebook_url_are_rejected_before_network(self):
        client = BrightDataClient("token", opener=lambda *_args, **_kwargs: self.fail())
        with self.assertRaises(ValueError):
            client.scrape_one("unknown", "https://www.facebook.com/page/posts/1")
        with self.assertRaises(ValueError):
            client.scrape_one(FACEBOOK_POST_DATASET, "https://example.com/post/1")

    def test_snapshot_is_polled_then_downloaded(self):
        payloads = iter([{"snapshot_id": "snap_1"}, {"status": "running"},
                         {"status": "ready"}, [{"comment_id": "c1"}]])

        def open_request(_request, timeout):
            return Response(json.dumps(next(payloads)).encode())

        result = BrightDataClient(
            "token", opener=open_request, sleeper=lambda _seconds: None
        ).scrape_one(FACEBOOK_COMMENTS_DATASET, "https://facebook.com/page/posts/1")
        self.assertEqual(result.snapshot_id, "snap_1")
        self.assertEqual(result.records, [{"comment_id": "c1"}])

    def test_http_error_does_not_expose_response_or_token(self):
        def open_request(request, timeout):
            response = io.BytesIO(json.dumps({
                "error": "invalid token do-not-leak", "message": "Check access",
                "validation_errors": [{"field": "limit", "message": "too small"}],
            }).encode())
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, response)

        client = BrightDataClient("do-not-leak", opener=open_request)
        with self.assertRaisesRegex(BrightDataError, "HTTP 401") as caught:
            client.scrape_one(FACEBOOK_POST_DATASET, "https://facebook.com/page/posts/1")
        self.assertNotIn("do-not-leak", str(caught.exception))
        self.assertIn("invalid token [redacted]", str(caught.exception))
        self.assertIn("too small", str(caught.exception))


class BrightDataQualityTests(unittest.TestCase):
    def test_report_proves_ingestion_and_repeat_offender_readiness_without_raw_text(self):
        posts = [{
            "post_id": "p1", "url": "https://facebook.com/p/1", "content": "Service update",
            "date_posted": "2026-09-01T10:00:00Z", "num_comments": 2,
        }]
        comments = [
            {"comment_id": "c1", "post_url": "https://facebook.com/p/1",
             "comment_text": "WhatsApp +92 300 1234567", "date_created": "2026-09-01",
             "user_id": "u1"},
            {"comment_id": "c2", "post_url": "https://facebook.com/p/1",
             "comment_text": "Please help", "date_created": "2026-09-01", "user_url": "u2"},
        ]
        report = quality_report(posts, comments)
        rendered = json.dumps(report)
        self.assertTrue(report["meaningful_for_ingestion"])
        self.assertTrue(report["supports_repeat_offender_hashing"])
        self.assertEqual(report["comments"]["scam_signal_candidates"], 1)
        self.assertNotIn("Please help", rendered)
        self.assertNotIn("300 1234567", rendered)


if __name__ == "__main__":
    unittest.main()
