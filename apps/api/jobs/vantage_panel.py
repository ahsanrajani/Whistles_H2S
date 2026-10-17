"""``vantage_panel`` job — the AI-listening panel run, off the request thread.

Every active prompt × every panel model is one sequential LLM call (6 × 5 = 30
by default), which takes minutes. Run synchronously it outlived the Next dev
proxy's 30 s socket, so the UI showed "Internal Server Error" while the run
carried on server-side — and each retry started another costed run. Same
``_jobs``/``_lock`` live-progress pattern as the ``seo_crawl`` job; the
frontend follows it with ``JobConsole``.
"""
from datetime import datetime, timezone

from .worker import handler

PREFIX = "vantage-"


def job_prefix(ws: int) -> str:
    return f"{PREFIX}{ws}-"


@handler("vantage_panel")
def run_panel_job(payload):
    import app as _app
    from core import vantage_panel

    job_id, ws = payload["job_id"], payload["ws"]
    lines: list[str] = []

    def log(msg):
        lines.append(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}  {msg}")
        with _app._lock:
            _app._jobs[job_id] = {"state": "running", "lines": lines[-40:]}

    c = _app.db_operator()
    try:
        vantage_panel.ensure_starter_prompts(c.session, ws)
        c.commit()
        out = vantage_panel.run(c.session, ws, _app.keys(ws), log=log)
        c.commit()
        log(f"done · asked {out['prompts']} prompt(s) × {out['models']} models — "
            f"{out['asked']} answered, {out['failed']} failed")
        state = "done"
    except Exception as e:
        log(f"failed · {e}")
        with _app._lock:
            _app._jobs[job_id] = {"state": "failed", "lines": lines[-40:]}
        raise                                   # let the job queue dead-letter it
    finally:
        c.close()
    with _app._lock:
        _app._jobs[job_id] = {"state": state, "lines": lines[-40:]}
    _app.audit(actor=payload.get("actor"), tenant_id=ws, action="vantage.panel_run", after=out)
    return out
