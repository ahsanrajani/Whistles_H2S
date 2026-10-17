"""Minimal outbound email (build plan §6 / P4.9).

Same shape as ``integrations/write``: a ``transport`` seam for tests, real
``smtplib`` when SMTP creds are present, and a mock mode otherwise that appends
to ``OUTBOX`` and returns ``delivered: False``. Report distribution is the only
caller today.
"""
OUTBOX: list[dict] = []

_SMTP_KEYS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM")


def is_configured(keys: dict | None) -> bool:
    k = keys or {}
    return all(k.get(x) for x in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


def send(*, to, subject, body, attachments=None, keys=None, transport=None) -> dict:
    """``to``: list of addresses. ``attachments``: list of
    ``(filename, bytes, mime)``. Returns a delivery result dict."""
    recipients = [a for a in (to or []) if a]
    if not recipients:
        raise ValueError("no recipients")
    record = {"to": recipients, "subject": subject, "body": body,
              "attachments": [a[0] for a in (attachments or [])]}

    if transport is not None:
        transport(record, attachments or [])
        return {"delivered": True, "transport": "custom", **record}

    if is_configured(keys):
        _smtp_send(keys, recipients, subject, body, attachments or [])
        return {"delivered": True, "transport": "smtp", **record}

    OUTBOX.append(record)
    return {"delivered": False, "transport": "mock", "outbox_size": len(OUTBOX),
            **record}


def _smtp_send(keys, recipients, subject, body, attachments):  # pragma: no cover
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = keys.get("SMTP_FROM") or keys["SMTP_USER"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    for filename, blob, mime in attachments:
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(blob, maintype=maintype, subtype=subtype or "octet-stream",
                           filename=filename)
    host, port = keys["SMTP_HOST"], int(keys.get("SMTP_PORT") or 587)
    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(keys["SMTP_USER"], keys["SMTP_PASSWORD"])
        s.send_message(msg)
