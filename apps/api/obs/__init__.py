"""Observability — structured logging (P1.9a), Prometheus metrics and the
health / readiness probes (P1.9b). Infrastructure only; nothing here knows
about the domain."""
from . import context
from .logs import JsonFormatter, configure_logging
from .logs import install as install_logging

__all__ = ["context", "JsonFormatter", "configure_logging", "install_logging"]
