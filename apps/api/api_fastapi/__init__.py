"""FastAPI-native routers — the P1.10 Flask → FastAPI migration.

Each module here defines an ``APIRouter`` that ``asgi.py`` mounts *above* the
Flask fallback, at the same paths and with the same behaviour as the Flask
router it replaces (which is dropped from ``api/__init__.py`` in the same
commit). Cross-cutting concerns — auth, RBAC, CSRF, the tenant-scoped DB handle
— are FastAPI dependencies in ``deps.py``, standing in for Flask's
``protect_portal`` + ``api/v1/common`` helpers for these routes.

The contract of record stays ``packages/contracts/openapi.yaml``; parity tests
(``tests/test_api_parity.py``) are what prove a port changed nothing.
"""
