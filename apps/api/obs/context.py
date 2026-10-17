"""Request-scoped correlation ids on contextvars, so any log record — from a
route, a repository, a worker — can be stamped with the request id and tenant
id without threading them through every call signature.
"""
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("guru_request_id", default=None)
_tenant_id: ContextVar[int | None] = ContextVar("guru_tenant_id", default=None)


def bind(*, request_id=None, tenant_id=None):
    """Set whichever ids are supplied for the current context."""
    if request_id is not None:
        _request_id.set(request_id)
    if tenant_id is not None:
        _tenant_id.set(tenant_id)


def clear():
    _request_id.set(None)
    _tenant_id.set(None)


def request_id():
    return _request_id.get()


def tenant_id():
    return _tenant_id.get()
