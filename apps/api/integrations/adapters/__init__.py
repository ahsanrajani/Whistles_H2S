"""Source adapters, one module per family. `core.collector` imports these to
build `REGISTRY`; each concrete adapter subclasses `core.collector.Adapter` and
reaches shared primitives (`_get`, `_h`, `QuotaExceeded`, the Bright Data budget
helpers) through the `core.collector` module so the tests' `@patch` seams hold.
"""
from .appstores import AppStoreReviews, PlayStoreReviews
from .brightdata import (BrightDataFacebookComments, BrightDataFacebookPosts,
                         BrightDataGoogleMapsReviews, BrightDataInstagramComments,
                         BrightDataInstagramPosts, BrightDataLinkedIn,
                         BrightDataQuora, BrightDataTikTok,
                         _BrightDataComments, _BrightDataOwnedChannel)
from .bright_data_serp import (BrightDataSerp, BrightDataSerpReddit,
                               BrightDataSerpX)
from .dataforseo import (DataForSEOBrandSerp, DataForSEOSerp, DataForSEOStandard,
                         DataForSEOWebBackfill)
from .meta import MetaBase, MetaFacebook, MetaInstagram
from .news import GoogleNews, RegulatoryWatch
from .places import GooglePlacesReviews
from .reddit import ArcticShift, RedditFree
from .social import Bluesky, XOwnedPosts, XRecent
from .video import YouTube, YouTubeOwnedVideos

__all__ = [
    "GoogleNews", "RegulatoryWatch", "ArcticShift", "RedditFree", "YouTube",
    "Bluesky", "XRecent", "DataForSEOStandard", "DataForSEOSerp",
    "DataForSEOBrandSerp", "AppStoreReviews", "PlayStoreReviews", "MetaBase",
    "MetaFacebook", "MetaInstagram", "BrightDataFacebookPosts",
    "_BrightDataComments", "BrightDataFacebookComments",
    "BrightDataInstagramComments", "BrightDataGoogleMapsReviews",
    "BrightDataInstagramPosts", "_BrightDataOwnedChannel", "BrightDataLinkedIn",
    "BrightDataTikTok", "BrightDataQuora",
    "BrightDataSerp", "BrightDataSerpX", "BrightDataSerpReddit",
    "DataForSEOWebBackfill", "GooglePlacesReviews", "YouTubeOwnedVideos",
    "XOwnedPosts",
]
