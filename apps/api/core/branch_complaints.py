"""Branch-complaint CSV import — a portal-only bulk-entry path for real
branch complaints that arrive as a spreadsheet rather than through a live
collector.

Rows are matched to a catalogue branch (``core.branch_resolver``), inserted as
ordinary ``item`` rows on a distinct, non-review surface so they never
inflate ``branch_perf``'s review counts/star ratings (P2.4's ``is_review``
gate), and attributed as explicit ``mention`` rows to the workspace's focus
brand. Sentiment/category are deliberately left unset here — the caller
enqueues a ``"scoring"`` job afterward and the existing scanners
(``sentiment.score_pending`` / ``classify.classify_pending``) fill them in,
same as any other newly collected mention.
"""
import csv
import hashlib
import io
import json
from datetime import datetime, timezone

from types import SimpleNamespace

from . import branch_resolver, entity
from .collector import norm

REQUIRED_HEADERS = ["Branch Name", "Complainant", "Complaint Date",
                    "Complaint Text (paraphrased)", "Source URL"]

SURFACE = "branch_complaint"
SOURCE = "branch_complaint_csv"
RULE = "branch_complaint_csv"

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                 "%B %d, %Y", "%d %B %Y", "%Y/%m/%d")


def _parse_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def parse_csv(raw_bytes):
    """(rows, header_error). ``rows`` is a list of dicts with the 5 raw
    string fields plus a 1-based ``_index`` (header row excluded, matching
    what a spreadsheet user would call "row 2", etc. — off by one from that
    on purpose, since ``_index`` counts data rows only, so callers should
    report it as "row {_index} of the data"). ``header_error`` is a message
    if the header line doesn't match ``REQUIRED_HEADERS`` exactly, else
    ``None``."""
    text_body = raw_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text_body))
    fields = [f.strip() for f in (reader.fieldnames or [])]
    if fields != REQUIRED_HEADERS:
        return [], (f"CSV headers must be exactly: {', '.join(REQUIRED_HEADERS)} "
                    f"(got: {', '.join(fields) or '(empty)'})")
    out = []
    for i, row in enumerate(reader, start=1):
        out.append({"_index": i, **{k: (v or "").strip() for k, v in row.items()}})
    return out, None


def import_rows(session, *, workspace_id, brand_id, rows):
    """Insert item+mention rows for each parsed CSV row.
    Returns {"inserted": n, "skipped": n, "errors": [{"row": i, "reason": str}]}.
    """
    from db import pipeline

    resolver = branch_resolver.for_workspace(SimpleNamespace(session=session), workspace_id)
    inserted = skipped = 0
    errors = []
    seen_urls = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for row in rows:
        idx = row["_index"]
        branch_name = row.get("Branch Name", "")
        complainant = row.get("Complainant", "")
        body = row.get("Complaint Text (paraphrased)", "")
        url = row.get("Source URL", "")

        if not body:
            errors.append({"row": idx, "reason": "empty complaint text"})
            skipped += 1
            continue

        hit = resolver.resolve_by_name(branch_name)
        if not hit:
            errors.append({"row": idx, "reason": f"no branch match for {branch_name!r}"})
            skipped += 1
            continue
        branch_key = hit[0]

        published_at = _parse_date(row.get("Complaint Date", "")) or now_iso

        row_url = url or None
        if row_url:
            n = seen_urls.get(row_url, 0)
            seen_urls[row_url] = n + 1
            if n:
                # Never give two items the same url (dedupe.py's exact-URL
                # pass would fold them into one, invisible to branch_perf).
                row_url = f"{row_url}#{branch_key}-{idx}"

        content_hash = hashlib.sha256(
            norm(f"{branch_key}|{complainant}|{published_at}|{body}").encode()
        ).hexdigest()[:32]
        external_id = f"csv-{content_hash}"

        raw_json = json.dumps({"branch_key": branch_key, "complainant": complainant or None})

        item_inserted = pipeline.insert_item(session, (
            workspace_id, SURFACE, SOURCE, "licensed", external_id, row_url,
            None, complainant or None, published_at, None, body,
            entity.guess_lang(body), None, 0,
            None, raw_json, now_iso, content_hash, 0, None, "third_party",
        ))
        if not item_inserted:
            skipped += 1
            errors.append({"row": idx, "reason": "duplicate of a previously uploaded row"})
            continue

        item_id = pipeline.item_id_by_external(session, workspace_id, SOURCE, external_id)
        if not item_id:
            skipped += 1
            errors.append({"row": idx, "reason": "insert failed"})
            continue

        pipeline.insert_mention(session, workspace_id, item_id, brand_id,
                                RULE, 0, 0, None)
        inserted += 1

    return {"inserted": inserted, "skipped": skipped, "errors": errors}
