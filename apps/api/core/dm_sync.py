"""Facebook Messenger / Instagram Direct Message ingestion.

The gap flagged earlier this session ("messages that fall in Requests") --
Message Requests are a separate inbox from public comments and were never
ingested at all, needing ``pages_messaging`` / ``instagram_manage_messages``
(confirmed granted 2026-09-10, verified live against the real Page).

A DM to the business inbox is unambiguously a real customer contact -- unlike
a public comment (core/care_bridge.py's complaint-keyword gate), nothing here
needs to guess whether it's actually a complaint. Every not-yet-seen inbound
message is routed straight into Care via ``cases.ingest_message()``; outbound
messages already sent by a human via Messenger/Instagram natively are
recorded too, so a case's timeline isn't missing half the conversation.

Polling, not webhooks (same posture as the rest of collection here) --
idempotent on ``case_message.platform_ref`` since ``ingest_message()`` itself
has no dedupe of its own.
"""
import json
import urllib.parse
from datetime import datetime

from sqlalchemy import text

from core import cases, collector, realtime
from db.repositories import scheduled_task

GRAPH = "https://graph.facebook.com/v20.0"
# The standalone "Instagram API with Instagram Login" product -- its own
# app/token, native host, no Page-token exchange. Root-caused 2026-09-16:
# the unified graph.facebook.com/{page_id}/conversations?platform=instagram
# route returns a persistent 500 ("reduce the amount of data...") for this
# account regardless of limit/fields; graph.instagram.com/{ig_user_id}/... on
# an INSTAGRAM_LOGIN_ACCESS_TOKEN was verified live to return the same shape
# of conversations/messages data successfully. Used when configured; falls
# back to the Facebook-Login path otherwise.
IG_GRAPH = "https://graph.instagram.com/v21.0"
_PLATFORMS = {"messenger": "facebook", "instagram": "instagram"}
_SYNC_CRON = "* * * * *"


def ensure_workspace_schedule(session, workspace_id) -> None:
    """Poll the two Meta inboxes once a minute for this workspace."""
    scheduled_task.register(
        session, name=f"meta-dm-sync:{workspace_id}", kind="dm_sync",
        cron=_SYNC_CRON, payload={"ws": workspace_id}, tenant_id=workspace_id)


def publish_events(result: dict, workspace_id: int) -> None:
    """Notify Care only after the caller has committed ingested messages."""
    for platform_result in result.values():
        for event in platform_result.get("events", []):
            realtime.publish(f"queue:{workspace_id}", {
                "kind": "meta_message", **event,
            })
            realtime.publish(f"case:{event['case_id']}", {
                "kind": "meta_message", "channel": event["channel"],
            })


def _get(url):
    return json.loads(collector._get(url, timeout=30))


def _page_token(keys: dict) -> tuple[str, str]:
    page_id, token = keys.get("META_PAGE_ID"), keys.get("META_ACCESS_TOKEN")
    if not (page_id and token):
        raise RuntimeError("META_PAGE_ID / META_ACCESS_TOKEN not configured")
    data = _get(f"{GRAPH}/me/accounts?access_token={urllib.parse.quote(token)}")
    for acct in data.get("data") or []:
        if str(acct.get("id")) == str(page_id) and acct.get("access_token"):
            return page_id, acct["access_token"]
    raise RuntimeError(f"no page-scoped token found for META_PAGE_ID={page_id}")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("+0000", "+00:00"))
    except ValueError:
        return None


def _already_seen(session, workspace_id: int, platform_ref: str) -> bool:
    return session.execute(text(
        "SELECT 1 FROM case_message WHERE workspace_id = :ws AND platform_ref = :ref"),
        {"ws": workspace_id, "ref": platform_ref}).first() is not None


def _sync_one(session, workspace_id: int, *, graph_host: str, conv_root: str, token: str,
              platform_qs: str | None, business_id: str, platform: str,
              limit_conversations: int, log) -> dict:
    """``business_id`` -- the id representing Chase's own side of a
    conversation on THIS platform -- is NOT always ``page_id``. Root-caused
    2026-09-11 (hamzaraza / C-117): Meta's unified Conversations API
    represents the business side as the Page id for Messenger threads, but
    as the linked IG Business Account id for Instagram threads, even though
    both are fetched via the same ``/{page_id}/conversations`` call.
    Filtering "not page_id" to find the real customer left Instagram's own
    business participant IN the list (its id never matched page_id) and
    excluded nothing -- silently picking Chase's own account as "the
    customer" whenever it sorted first, and misreading every Instagram
    message's direction as inbound (a from_id of ig_user_id never matched
    page_id either).

    ``graph_host``/``conv_root``/``token``/``platform_qs`` vary by route: the
    Facebook-Login path hits ``graph.facebook.com/{page_id}/...`` with a
    ``platform=`` filter on the shared Page token; the Instagram-Login path
    hits ``graph.instagram.com/{ig_user_id}/...`` directly on its own token,
    with no ``platform=`` filter needed (the host is IG-native)."""
    care_platform = _PLATFORMS[platform]
    channel = "messenger" if platform == "messenger" else "instagram_dm"

    url = (f"{graph_host}/{conv_root}/conversations?fields=participants"
           f"&limit={limit_conversations}")
    if platform_qs:
        url += f"&platform={platform_qs}"
    url += f"&access_token={urllib.parse.quote(token)}"
    convs = _get(url)
    scanned = ingested = 0
    events = []
    for conv in convs.get("data") or []:
        others = [p for p in (conv.get("participants") or {}).get("data", [])
                 if str(p.get("id")) != str(business_id)]
        customer = others[0] if others else {}
        # The Instagram-Login route's participants only carry `username`, not
        # `name` (the Facebook-Login route's field) -- without this fallback
        # every Instagram-Login-sourced customer's display_name stayed NULL
        # and Care fell back to showing the raw numeric IGSID as the handle.
        customer_name = customer.get("name") or customer.get("username")
        msgs = _get(f"{graph_host}/{conv['id']}/messages?fields=from,message,created_time"
                    f"&access_token={urllib.parse.quote(token)}")
        for m in msgs.get("data") or []:
            scanned += 1
            ref = m.get("id")
            if not ref or _already_seen(session, workspace_id, ref):
                continue
            from_id = str((m.get("from") or {}).get("id") or "")
            direction = "outbound" if from_id == str(business_id) else "inbound"
            result = cases.ingest_message(
                session, workspace_id, platform=care_platform, channel=channel,
                handle=customer.get("id"), display_name=customer_name,
                body=m.get("message") or "",
                sent_at=_parse_time(m.get("created_time")),
                direction=direction, platform_ref=ref,
                actor="system" if direction == "inbound" else None)
            ingested += 1
            if direction == "inbound":
                events.append({"case_id": result["case_id"], "channel": channel,
                               "new_case": result["new"]})
    log(f"{platform} · {len(convs.get('data') or [])} conversation(s), "
        f"{scanned} message(s) scanned, {ingested} new")
    return {"scanned": scanned, "ingested": ingested, "events": events}


def sync(session, workspace_id: int, keys: dict, *,
         limit_conversations: int = 25, log=None) -> dict:
    """One real, read-only poll of the Page's Messenger + Instagram DM
    conversation threads. Best-effort per platform -- Instagram DMs need a
    connected IG Business Account on the same Page, which not every
    workspace has; a failure there doesn't block Messenger.

    Instagram prefers ``INSTAGRAM_LOGIN_ACCESS_TOKEN`` (the standalone
    Instagram-Login route) when configured -- it needs no Page-token
    exchange at all, so it keeps working even when the Facebook Page token
    is itself rate-limited or the Facebook-Login conversations call is
    500ing. Falls back to the shared Page token otherwise (unchanged
    behaviour for workspaces without the new credential)."""
    log = log or (lambda *_a: None)

    page_id = page_token = None
    ig_login_token = keys.get("INSTAGRAM_LOGIN_ACCESS_TOKEN")
    try:
        page_id, page_token = _page_token(keys)
    except Exception:                                              # noqa: BLE001
        if not ig_login_token:
            raise   # no fallback available -- unchanged hard-fail contract
        page_err = "Facebook Page token unavailable (Instagram is using its own login token)"
    else:
        page_err = None

    out: dict = {}
    if page_id is not None:
        try:
            out["messenger"] = _sync_one(
                session, workspace_id, graph_host=GRAPH, conv_root=page_id,
                token=page_token, platform_qs="messenger", business_id=page_id,
                platform="messenger", limit_conversations=limit_conversations, log=log)
        except Exception as exc:                                    # noqa: BLE001
            log(f"messenger · failed ({exc})")
            out["messenger"] = {"scanned": 0, "ingested": 0, "error": str(exc)}
    else:
        out["messenger"] = {"scanned": 0, "ingested": 0, "error": page_err}

    ig_user_id = keys.get("META_IG_USER_ID")
    if not ig_user_id:
        out["instagram"] = {"scanned": 0, "ingested": 0,
                            "error": "META_IG_USER_ID not configured"}
    else:
        if ig_login_token:
            ig_host, ig_root, ig_token, ig_platform_qs = IG_GRAPH, ig_user_id, ig_login_token, None
        elif page_id is not None:
            ig_host, ig_root, ig_token, ig_platform_qs = GRAPH, page_id, page_token, "instagram"
        else:
            ig_host = None
        if ig_host is None:
            out["instagram"] = {"scanned": 0, "ingested": 0, "error": page_err}
        else:
            try:
                out["instagram"] = _sync_one(
                    session, workspace_id, graph_host=ig_host, conv_root=ig_root,
                    token=ig_token, platform_qs=ig_platform_qs, business_id=ig_user_id,
                    platform="instagram", limit_conversations=limit_conversations, log=log)
            except Exception as exc:                                # noqa: BLE001
                log(f"instagram · failed ({exc})")
                out["instagram"] = {"scanned": 0, "ingested": 0, "error": str(exc)}
    return out
