"""YouTube Data API v3 — video results plus their top-level comment threads."""
import json
import time
import urllib.parse

from core import collector


class YouTube(collector.Adapter):
    ID = "youtube_v3"

    def fetch(self, terms):
        key = self.k["YOUTUBE_API_KEY"]
        for term in terms[:4]:
            url = ("https://www.googleapis.com/youtube/v3/search?part=snippet"
                   f"&q={urllib.parse.quote(term)}&maxResults=25&type=video"
                   f"&relevanceLanguage=en&regionCode=PK&key={key}")
            try:
                d = json.loads(collector._get(url, timeout=45))
                self.count(self.ID, units=100)
            except Exception as e:
                self.count(self.ID, ok=False)
                self.log(f"youtube · {term} failed ({e})")
                continue
            items = d.get("items", [])
            self.log(f"youtube · {term} · {len(items)}")
            for it in items:
                sn = it.get("snippet", {})
                vid = (it.get("id") or {}).get("videoId")
                if not vid:
                    # No video id (e.g. a channel/playlist result slipping past
                    # type=video) means no real URL to link to — skip rather
                    # than yield a dead item.
                    continue
                yield {"external_id": vid,
                       "url": f"https://youtube.com/watch?v={vid}",
                       "outlet": sn.get("channelTitle"), "author": sn.get("channelTitle"),
                       "published_at": sn.get("publishedAt"),
                       "title": sn.get("title"),
                       "body": (sn.get("title") or "") + " " + (sn.get("description") or ""),
                       "raw": {"term": term}}
                comments_url = (
                    "https://www.googleapis.com/youtube/v3/commentThreads"
                    f"?part=snippet&videoId={vid}&maxResults=100&textFormat=plainText&key={key}")
                try:
                    comments = json.loads(collector._get(comments_url, timeout=45)).get("items", [])
                    self.count(self.ID, units=1)
                except Exception as e:
                    self.count(self.ID, ok=False)
                    self.log(f"youtube comments · {vid} failed ({e})")
                    continue
                for thread in comments:
                    comment = (thread.get("snippet") or {}).get("topLevelComment", {})
                    cid = comment.get("id")
                    detail = comment.get("snippet") or {}
                    yield {"external_id": f"comment:{cid}",
                           "url": (f"https://youtube.com/watch?v={vid}&lc={cid}"
                                   if cid else f"https://youtube.com/watch?v={vid}"),
                           "outlet": sn.get("channelTitle"),
                           "author": detail.get("authorDisplayName"),
                           "published_at": detail.get("publishedAt"),
                           "title": sn.get("title"), "body": detail.get("textDisplay"),
                           "raw": {"term": term, "video_id": vid, "kind": "comment"}}
            time.sleep(0.4)


class YouTubeOwnedVideos(collector.Adapter):
    """The channel's own recent uploads, with real view/like/comment counts.
    `terms` is unused -- this is the owned channel by id, not a search."""
    ID = "youtube_owned_videos"

    def fetch(self, terms):
        key = self.k["YOUTUBE_API_KEY"]
        channel_id = self.k["YOUTUBE_CHANNEL_ID"]
        try:
            ch = json.loads(collector._get(
                "https://www.googleapis.com/youtube/v3/channels"
                f"?part=contentDetails&id={channel_id}&key={key}", timeout=30))
            self.count(self.ID, units=1)
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"youtube owned · channel lookup failed ({e})")
            return
        items = ch.get("items") or []
        uploads = (((items[0] if items else {}).get("contentDetails") or {})
                  .get("relatedPlaylists") or {}).get("uploads")
        if not uploads:
            self.log("youtube owned · no uploads playlist for this channel id")
            return
        try:
            playlist = json.loads(collector._get(
                "https://www.googleapis.com/youtube/v3/playlistItems"
                f"?part=snippet&playlistId={uploads}&maxResults=25&key={key}", timeout=30))
            self.count(self.ID, units=1)
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"youtube owned · playlist failed ({e})")
            return
        entries = playlist.get("items") or []
        vids = [e["snippet"]["resourceId"]["videoId"] for e in entries
               if (e.get("snippet") or {}).get("resourceId", {}).get("videoId")]
        if not vids:
            self.log("youtube owned · 0 uploads")
            return
        try:
            stats = json.loads(collector._get(
                "https://www.googleapis.com/youtube/v3/videos"
                f"?part=statistics&id={','.join(vids)}&key={key}", timeout=30))
            self.count(self.ID, units=1)
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"youtube owned · stats failed ({e})")
            stats = {"items": []}
        stats_by_id = {s["id"]: s.get("statistics") or {} for s in stats.get("items") or []}
        self.log(f"youtube owned · {len(entries)} uploads")
        for e in entries:
            sn = e.get("snippet") or {}
            vid = (sn.get("resourceId") or {}).get("videoId")
            if not vid:
                continue
            st = stats_by_id.get(vid, {})

            def _int(field):
                v = st.get(field)
                return int(v) if v is not None else None

            post_id = f"video:{vid}"
            yield {"external_id": post_id,
                   "url": f"https://youtube.com/watch?v={vid}",
                   "outlet": sn.get("channelTitle"), "author": sn.get("channelTitle"),
                   "published_at": sn.get("publishedAt"), "title": sn.get("title"),
                   "body": sn.get("description"),
                   "raw": {"kind": "post", "metrics": {
                       "views": _int("viewCount"), "likes": _int("likeCount"),
                       "comments": _int("commentCount")},
                       "media": {"type": "youtube", "video_id": vid,
                                "image": (sn.get("thumbnails") or {}).get("high", {}).get("url")}}}
            comments_url = (
                "https://www.googleapis.com/youtube/v3/commentThreads"
                f"?part=snippet,replies&videoId={vid}&maxResults=50&textFormat=plainText&key={key}")
            try:
                threads = json.loads(collector._get(comments_url, timeout=45)).get("items", [])
                self.count(self.ID, units=1)
            except Exception as e:
                self.count(self.ID, ok=False)
                self.log(f"youtube owned · comments for {vid} failed ({e})")
                continue
            for thread in threads:
                top = (thread.get("snippet") or {}).get("topLevelComment", {})
                cid = top.get("id")
                detail = top.get("snippet") or {}
                if cid and detail.get("textDisplay"):
                    yield {"external_id": f"comment:{cid}",
                           "url": f"https://youtube.com/watch?v={vid}&lc={cid}",
                           "outlet": sn.get("channelTitle"),
                           "author": detail.get("authorDisplayName"),
                           "published_at": detail.get("publishedAt"), "title": None,
                           "body": detail.get("textDisplay"),
                           "raw": {"kind": "comment", "parent_id": post_id}}
                for reply in (thread.get("replies") or {}).get("comments") or []:
                    rid = reply.get("id")
                    rdetail = reply.get("snippet") or {}
                    if not rid or not rdetail.get("textDisplay"):
                        continue
                    yield {"external_id": f"comment:{rid}",
                           "url": f"https://youtube.com/watch?v={vid}&lc={rid}",
                           "outlet": sn.get("channelTitle"),
                           "author": rdetail.get("authorDisplayName"),
                           "published_at": rdetail.get("publishedAt"), "title": None,
                           "body": rdetail.get("textDisplay"),
                           "raw": {"kind": "reply", "parent_id": f"comment:{cid}"}}
