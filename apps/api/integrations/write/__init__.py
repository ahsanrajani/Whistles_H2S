"""Write-integration layer (P3.1) — outbound actions to external platforms."""
from . import base
from .base import (ACTIONS, WriteClient, WriteError, WriteRejected, WriteResult,
                   live_enabled)
from .platforms import (CLIENTS, GoogleReviewsWriteClient, LinkedInWriteClient,
                        MetaWriteClient, XWriteClient, YouTubeWriteClient,
                        client_for)

__all__ = [
    "ACTIONS", "WriteClient", "WriteError", "WriteRejected", "WriteResult",
    "live_enabled", "base", "CLIENTS", "client_for", "MetaWriteClient",
    "XWriteClient", "LinkedInWriteClient", "GoogleReviewsWriteClient",
    "YouTubeWriteClient",
]
