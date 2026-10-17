"""Run one bounded Bright Data Facebook post/data-quality probe."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.bright_data import (  # noqa: E402
    FACEBOOK_COMMENTS_DATASET,
    FACEBOOK_POST_DATASET,
    BrightDataClient,
    BrightDataError,
)


SIGNAL_PATTERN = re.compile(
    r"(?:\+?\d[\d\s().-]{7,}\d|\bwhatsapp\b|wa\.me/|bit\.ly/|tinyurl\.com/|t\.co/)",
    re.IGNORECASE,
)


def _coverage(rows: list[dict[str, Any]], field: str) -> float:
    if not rows:
        return 0.0
    present = sum(value not in (None, "", []) for value in (row.get(field) for row in rows))
    return round(present / len(rows), 3)


def quality_report(
    posts: list[dict[str, Any]], comments: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Summarise usefulness without echoing public users' raw content."""
    comments_requested = comments is not None
    comments = comments or []
    scam_signals = sum(
        bool(SIGNAL_PATTERN.search(str(row.get("comment_text") or ""))) for row in comments
    )
    report = {
        "paid_records_returned": len(posts) + len(comments),
        "post": {
            "records": len(posts),
            "id_coverage": _coverage(posts, "post_id"),
            "url_coverage": _coverage(posts, "url"),
            "text_coverage": _coverage(posts, "content"),
            "timestamp_coverage": _coverage(posts, "date_posted"),
            "engagement_coverage": max(
                _coverage(posts, "num_comments"), _coverage(posts, "likes")
            ),
        },
        "comments": {
            "requested": comments_requested,
            "records": len(comments),
            "id_coverage": _coverage(comments, "comment_id"),
            "post_url_coverage": _coverage(comments, "post_url"),
            "text_coverage": _coverage(comments, "comment_text"),
            "timestamp_coverage": _coverage(comments, "date_created"),
            "actor_identity_coverage": max(
                _coverage(comments, "user_id"), _coverage(comments, "user_url")
            ),
            "reply_linkage_coverage": _coverage(comments, "parent_comment_id"),
            "scam_signal_candidates": scam_signals,
        },
    }
    post_ready = bool(posts) and all(
        report["post"][key] >= 0.8
        for key in ("id_coverage", "url_coverage", "text_coverage", "timestamp_coverage")
    )
    comment_ready = not comments_requested or (
        bool(comments)
        and report["comments"]["text_coverage"] >= 0.8
        and report["comments"]["actor_identity_coverage"] >= 0.5
    )
    report["meaningful_for_ingestion"] = post_ready and comment_ready
    report["supports_repeat_offender_hashing"] = bool(comments) and (
        report["comments"]["actor_identity_coverage"] >= 0.5
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe one known Facebook post through Bright Data without saving raw data."
    )
    parser.add_argument("post_url", help="Canonical URL of one public Facebook post")
    parser.add_argument(
        "--include-comments",
        action="store_true",
        help="Also fetch comments; provider billing varies with records returned.",
    )
    parser.add_argument(
        "--accept-variable-record-cost",
        action="store_true",
        help="Required with --include-comments because the endpoint has no record cap.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.include_comments and not args.accept_variable_record_cost:
        print(
            "Refusing comment collection without --accept-variable-record-cost; "
            "the provider endpoint has no per-request record cap.",
            file=sys.stderr,
        )
        return 2
    load_dotenv(ROOT / ".env", override=True)
    token = os.environ.get("BRIGHT_DATA_API_KEY")
    if not token:
        print("BRIGHT_DATA_API_KEY is missing from the environment or ignored .env", file=sys.stderr)
        return 2

    client = BrightDataClient(token)
    try:
        posts = client.scrape_one(FACEBOOK_POST_DATASET, args.post_url).records
        comments = None
        if args.include_comments:
            comments = client.scrape_one(FACEBOOK_COMMENTS_DATASET, args.post_url).records
    except (BrightDataError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(quality_report(posts, comments), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

