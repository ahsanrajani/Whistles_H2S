"""Small, cost-conscious client for Bright Data Web Scraper API probes.

Production collectors should build on this client only after a dataset has passed
the field-quality probe. Tokens are accepted through configuration and are never
included in URLs, exceptions, or reports.
"""
from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


API_ROOT = "https://api.brightdata.com/datasets/v3"
FACEBOOK_POST_DATASET = "gd_lyclm1571iy3mv57zw"
FACEBOOK_COMMENTS_DATASET = "gd_lkay758p1eanlolqw8"
FACEBOOK_PAGE_POSTS_DATASET = "gd_lkaxegm826bjpoo9m5"
# Instagram dataset ids follow Bright Data's published catalogue; not yet
# confirmed against this account. First real run must use a tiny USD cap.
INSTAGRAM_POSTS_DATASET = "gd_lk5ns7kz21pck8jpis"
INSTAGRAM_COMMENTS_DATASET = "gd_ltppn085pokosxh13"


class BrightDataError(RuntimeError):
    """A provider failure with credentials and response bodies kept private."""


@dataclass(frozen=True)
class BrightDataResult:
    records: list[dict[str, Any]]
    snapshot_id: str | None = None


class BrightDataClient:
    def __init__(
        self,
        token: str,
        *,
        timeout: int = 60,
        poll_interval: float = 2.0,
        max_poll_seconds: int = 180,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not token or any(char in token for char in "\r\n"):
            raise ValueError("A single-line Bright Data API token is required")
        self._token = token
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_poll_seconds = max_poll_seconds
        self._open = opener
        self._sleep = sleeper

    def scrape_one(self, dataset_id: str, target_url: str) -> BrightDataResult:
        """Scrape exactly one canonical URL from an allow-listed dataset."""
        if dataset_id not in {FACEBOOK_POST_DATASET, FACEBOOK_COMMENTS_DATASET}:
            raise ValueError("Dataset is not approved for the bounded probe")
        parsed = urllib.parse.urlparse(target_url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "facebook.com", "www.facebook.com", "web.facebook.com"
        }:
            raise ValueError("Probe target must be a canonical HTTPS Facebook URL")

        return self._trigger(dataset_id, [{"url": target_url}], {
            "format": "json",
            "include_errors": "true",
        })

    def discover_facebook_page_posts(
        self, page_username: str, limit: int
    ) -> BrightDataResult:
        """Discover a bounded number of posts from one configured Facebook page."""
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", page_username or ""):
            raise ValueError("Facebook page username is invalid")
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Facebook page-post limit must be between 1 and 100")
        return self._scrape_or_snapshot(
            FACEBOOK_PAGE_POSTS_DATASET, [{"user_name": page_username}], {
            "format": "json",
            "include_errors": "true",
            "type": "discover_new",
            "discover_by": "user_name",
            "limit_per_input": str(limit),
        })

    def discover_instagram_profile_posts(
        self, username: str, limit: int
    ) -> BrightDataResult:
        """Discover a bounded number of posts from one configured Instagram profile."""
        if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", username or ""):
            raise ValueError("Instagram username is invalid")
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Instagram post limit must be between 1 and 100")
        return self._scrape_or_snapshot(
            INSTAGRAM_POSTS_DATASET, [{"user_name": username}], {
            "format": "json",
            "include_errors": "true",
            "type": "discover_new",
            "discover_by": "user_name",
            "limit_per_input": str(limit),
        })

    def discover_owned_posts(
        self, dataset_id: str, target: str, limit: int
    ) -> BrightDataResult:
        """Discover a bounded number of posts for one owned channel from *any*
        configured dataset. Used by the config-gated LinkedIn / TikTok / Quora /
        Google-Maps adapters (P2.6) — each dormant until a verified dataset id is
        set, so no adapter code changes to bring one live."""
        if not re.fullmatch(r"gd_[a-z0-9]{6,40}", (dataset_id or "").strip()):
            raise ValueError("Bright Data dataset id is invalid")
        if not (target or "").strip():
            raise ValueError("owned-channel target is required")
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("post limit must be between 1 and 100")
        return self._trigger(dataset_id, [{"user_name": target.strip()}], {
            "include_errors": "true",
            "type": "discover_new",
            "discover_by": "user_name",
            "limit_per_input": str(limit),
        })

    def collect_facebook_post_comments(
        self, post_urls: list[str], limit_per_post: int
    ) -> BrightDataResult:
        """Collect a bounded number of comments for specific Facebook post URLs."""
        return self._collect_post_comments(
            FACEBOOK_COMMENTS_DATASET, "Facebook",
            {"facebook.com", "www.facebook.com", "web.facebook.com"},
            post_urls, limit_per_post,
        )

    def collect_instagram_post_comments(
        self, post_urls: list[str], limit_per_post: int
    ) -> BrightDataResult:
        """Collect a bounded number of comments for specific Instagram post URLs."""
        return self._collect_post_comments(
            INSTAGRAM_COMMENTS_DATASET, "Instagram",
            {"instagram.com", "www.instagram.com"},
            post_urls, limit_per_post,
        )

    def _collect_post_comments(
        self, dataset_id: str, network: str, hosts: set[str],
        post_urls: list[str], limit_per_post: int,
    ) -> BrightDataResult:
        """Trigger a comments dataset for specific post URLs.

        These datasets have no provider-side per-request record cap, so the
        caller must bound both the number of inputs and the per-post count. The
        limit is sent to the provider (`limit_records` per input) and must also
        be re-applied to the returned rows by the caller.
        """
        if not post_urls:
            raise ValueError(f"At least one {network} post URL is required")
        if len(post_urls) > 25:
            raise ValueError("Refusing more than 25 comment inputs in one request")
        if not isinstance(limit_per_post, int) or not 1 <= limit_per_post <= 500:
            raise ValueError("Comment per-post limit must be between 1 and 500")
        inputs = []
        for url in post_urls:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in hosts:
                raise ValueError(
                    f"Every comment input must be a canonical HTTPS {network} URL"
                )
            inputs.append({"url": url, "limit_records": limit_per_post})
        return self._trigger(dataset_id, inputs, {
            "format": "json",
            "include_errors": "true",
        })

    def _scrape_or_snapshot(
        self, dataset_id: str, inputs: list[dict[str, Any]], params: dict[str, str]
    ) -> BrightDataResult:
        """Use a scraper-specific sync route that may fall back to a snapshot."""
        query = urllib.parse.urlencode({"dataset_id": dataset_id, **params})
        payload = self._json_request(
            f"{API_ROOT}/scrape?{query}",
            data=json.dumps({"input": inputs}).encode("utf-8"),
        )
        if isinstance(payload, dict) and payload.get("snapshot_id"):
            snapshot_id = str(payload["snapshot_id"])
            return BrightDataResult(self._await_snapshot(snapshot_id), snapshot_id)
        return BrightDataResult(self._records(payload))

    def _trigger(
        self, dataset_id: str, inputs: list[dict[str, Any]], params: dict[str, str]
    ) -> BrightDataResult:
        query = urllib.parse.urlencode({
            "dataset_id": dataset_id,
            **params,
        })
        payload = self._json_request(
            f"{API_ROOT}/trigger?{query}",
            data=json.dumps(inputs).encode("utf-8"),
        )
        if not isinstance(payload, dict) or not payload.get("snapshot_id"):
            raise BrightDataError("Bright Data did not return a snapshot ID")
        snapshot_id = str(payload["snapshot_id"])
        return BrightDataResult(self._await_snapshot(snapshot_id), snapshot_id)

    def _await_snapshot(self, snapshot_id: str) -> list[dict[str, Any]]:
        deadline = time.monotonic() + self.max_poll_seconds
        while time.monotonic() < deadline:
            progress = self._json_request(f"{API_ROOT}/progress/{snapshot_id}")
            status = str(progress.get("status", "")).lower() if isinstance(progress, dict) else ""
            if status == "ready":
                query = urllib.parse.urlencode({"format": "json"})
                payload = self._json_request(
                    f"{API_ROOT}/snapshot/{snapshot_id}?{query}"
                )
                return self._records(payload)
            if status in {"failed", "error"}:
                raise BrightDataError(f"Bright Data snapshot {snapshot_id} failed")
            self._sleep(self.poll_interval)
        raise BrightDataError(f"Bright Data snapshot {snapshot_id} was not ready in time")

    def _json_request(self, url: str, data: bytes | None = None) -> Any:
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "guru-ears/bright-data-probe",
            },
            method="POST" if data is not None else "GET",
        )
        try:
            with self._open(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = self._safe_http_error_detail(exc)
            suffix = f": {detail}" if detail else ""
            raise BrightDataError(
                f"Bright Data request failed with HTTP {exc.code}{suffix}"
            ) from exc
        except urllib.error.URLError as exc:
            raise BrightDataError("Bright Data request could not connect") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise BrightDataError("Bright Data request timed out") from exc
        except (json.JSONDecodeError, TypeError) as exc:
            raise BrightDataError("Bright Data returned invalid JSON") from exc

    def _safe_http_error_detail(self, exc: urllib.error.HTTPError) -> str:
        """Return only provider error metadata, with the configured token redacted."""
        try:
            payload = json.loads(exc.read())
        except (AttributeError, json.JSONDecodeError, TypeError, ValueError):
            return ""
        finally:
            exc.close()
        if not isinstance(payload, dict):
            return ""
        values = [payload.get(key) for key in (
            "code", "error", "message", "validation_errors"
        )]
        detail = " - ".join(
            json.dumps(value, ensure_ascii=True) if isinstance(value, (dict, list))
            else str(value)
            for value in values if value not in (None, "", [], {})
        )
        return detail.replace(self._token, "[redacted]")[:240]

    @staticmethod
    def _records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            if payload.get("error") or payload.get("errors"):
                raise BrightDataError("Bright Data returned an error record")
            payload = [payload]
        if not isinstance(payload, list):
            raise BrightDataError("Bright Data returned an unexpected response shape")
        return [row for row in payload if isinstance(row, dict) and not row.get("error")]
