"""Content calendar media uploads -- real picture/video files, not
paste-a-URL. Saved to local disk under ``static/uploads/<workspace>/`` (same
posture as the existing ``static/brand/`` logo serving in app.py) and served
back at ``/uploads/<workspace>/<file>`` via the Next dev-proxy rewrite, same
pattern as ``/brand/:path*``. A cloud object store is a natural swap once the
app leaves local, same note as the live credentials -- this is not it yet.
"""
import os
import uuid

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_ROOT = os.path.join(HERE, "static", "uploads")

MAX_BYTES = 50 * 1024 * 1024  # 50MB -- generous for a short vertical video
_EXT_BY_TYPE = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "video/mp4": ".mp4", "video/quicktime": ".mov",
}


class UploadError(Exception):
    pass


def save(workspace_id: int, *, filename: str, content_type: str, data: bytes) -> dict:
    """Validate and persist one file. Returns ``{url, filename, content_type,
    size}`` -- ``url`` is the frontend-facing path (``/uploads/...``), not
    the disk path."""
    ext = _EXT_BY_TYPE.get((content_type or "").lower())
    if not ext:
        raise UploadError(
            f"unsupported file type {content_type!r} -- allowed: "
            + ", ".join(sorted(_EXT_BY_TYPE)))
    if len(data) > MAX_BYTES:
        raise UploadError(f"file too large ({len(data)} bytes, max {MAX_BYTES})")
    if not data:
        raise UploadError("empty file")

    ws_dir = os.path.join(UPLOAD_ROOT, str(workspace_id))
    os.makedirs(ws_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(ws_dir, stored_name), "wb") as f:
        f.write(data)

    return {"url": f"/uploads/{workspace_id}/{stored_name}",
           "filename": filename or stored_name,
           "content_type": content_type, "size": len(data)}
