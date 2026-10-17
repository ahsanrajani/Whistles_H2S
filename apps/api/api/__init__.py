"""Versioned JSON API — historical Flask home.

Every route group moved to FastAPI in P1.10 (`api_fastapi/`, mounted in
`asgi.py`): admin, alerts, analysis, auth, branches, calibration, dashboards,
jobs, mentions, onboarding, report, tenancy. `bp` is now an empty blueprint,
kept only so `app.py`'s `register_blueprint(bp)` and `api/v1/common`
(`required_permission`) keep importing until the Flask app is retired.
"""
from .v1.common import bp

__all__ = ["bp"]
