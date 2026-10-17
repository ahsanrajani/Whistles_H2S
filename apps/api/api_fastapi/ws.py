"""Realtime WebSocket endpoint (frontend F0.4).

One socket per browser tab. The client sends ``{"type":"subscribe","topics":[…]}``
(and ``ping``); the server streams ``{"topic","ts","data"}`` frames from
``core.realtime.hub``. Auth is the shared session cookie — an unauthenticated
socket is closed 4401. A client may only subscribe to its own workspace's
``queue:``/``presence:`` topics; ``case:{id}`` is allowed through (the case
lists are already workspace-scoped server-side).
"""
import asyncio
import json

import websession
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core import realtime

router = APIRouter()


def _session_for(sock: WebSocket) -> dict:
    sid = sock.cookies.get(websession.COOKIE_NAME)
    if not sid:
        return {}
    try:
        return websession.store().load(sid) or {}
    except Exception:
        return {}


def _allowed(topics, ws_id: int) -> list[str]:
    ok = []
    for topic in topics:
        if not isinstance(topic, str):
            continue
        if topic.startswith("case:"):
            ok.append(topic)
        elif topic in (f"queue:{ws_id}", f"presence:{ws_id}"):
            ok.append(topic)
    return ok


async def _pump(sock: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        frame = await queue.get()
        await sock.send_text(json.dumps(frame))


@router.websocket("/api/v1/ws")
async def realtime_ws(sock: WebSocket) -> None:
    session = _session_for(sock)
    ws_id = session.get("ws_id")
    if "user_id" not in session or ws_id is None:
        await sock.close(code=4401)
        return

    await sock.accept()
    cid, queue = realtime.hub.register()
    sender = asyncio.create_task(_pump(sock, queue))
    await sock.send_text(json.dumps({"type": "ready", "workspace_id": ws_id}))

    try:
        while True:
            raw = await sock.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            kind = msg.get("type")
            if kind == "subscribe":
                realtime.hub.set_topics(cid, _allowed(msg.get("topics") or [], ws_id))
            elif kind == "ping":
                await sock.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        realtime.hub.unregister(cid)
