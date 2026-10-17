"""Meta Graph API adapters — the focus brand's own Facebook Page feed and
Instagram media, each with a slice of their comments."""
import json
import urllib.parse

from core import collector


class MetaBase(collector.Adapter):
    """Meta Graph API. Emits one item per post/media and one per comment.
    `terms` is unused: these are the brand's own channels."""
    GRAPH = "https://graph.facebook.com/v20.0"
    SURFACE_OUTLET = None

    def _graph(self, path, *, token=None, **params):
        params["access_token"] = token or self.k["META_ACCESS_TOKEN"]
        url = f"{self.GRAPH}/{path}?" + urllib.parse.urlencode(params)
        return json.loads(collector._get(url, timeout=45))

    def _paginate(self, path, *, token=None, max_pages=4, **params):
        """Follow Graph API cursor pagination for up to `max_pages` pages,
        yielding each page's `data` list. A single unpaginated page (the
        previous behaviour) only ever sees the ~50 most recent items --
        for an account with more posts than that, older ones (and any new
        comments landing on them) were never looked at again, ever. Bounded
        rather than unbounded: a comments-nested feed fetch gets expensive
        fast, and Meta's own rate limits make an unbounded crawl risky."""
        url = f"{self.GRAPH}/{path}?" + urllib.parse.urlencode(
            {**params, "access_token": token or self.k["META_ACCESS_TOKEN"]})
        for _ in range(max_pages):
            data = json.loads(collector._get(url, timeout=45))
            yield data.get("data") or []
            next_url = (data.get("paging") or {}).get("next")
            if not next_url:
                return
            url = next_url

    def _page_token(self):
        """Meta's "new Pages experience" rejects a user/system-user token on
        Page-feed calls ("A Page access token is required") -- exchange it
        for the Page-scoped token via /me/accounts, matched on META_PAGE_ID.
        Cached per adapter instance (one call per fetch(), not per page)."""
        if getattr(self, "_page_token_cache", None):
            return self._page_token_cache
        page_id = self.k.get("META_PAGE_ID")
        url = (f"{self.GRAPH}/me/accounts?access_token="
               + urllib.parse.quote(self.k["META_ACCESS_TOKEN"]))
        data = json.loads(collector._get(url, timeout=30))
        for acct in data.get("data") or []:
            if str(acct.get("id")) == str(page_id) and acct.get("access_token"):
                self._page_token_cache = acct["access_token"]
                return self._page_token_cache
        raise RuntimeError(
            f"no page-scoped token found for META_PAGE_ID={page_id} in /me/accounts")

    def _emit(self, external_id, url, author, when, text, kind, metrics=None,
             parent_id=None, media=None):
        raw = {"kind": kind}
        if metrics:
            raw["metrics"] = metrics
        if parent_id:
            raw["parent_id"] = parent_id
        if media:
            raw["media"] = media
        return {"external_id": external_id, "url": url, "outlet": self.SURFACE_OUTLET,
                "author": author, "published_at": when, "title": None,
                "body": text, "raw": raw}


class MetaFacebook(MetaBase):
    ID = "meta_facebook"
    SURFACE_OUTLET = "Facebook"

    def fetch(self, terms):
        try:
            page_token = self._page_token()
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"facebook · page token exchange failed ({e})")
            return
        try:
            posts, pages = [], 0
            for page in self._paginate(
                    f"{self.k['META_PAGE_ID']}/feed", token=page_token, limit=50,
                    fields="message,permalink_url,created_time,from{name},full_picture,"
                           "attachments{media_type},"
                           "likes.summary(true).limit(0),comments.summary(true).limit(50){"
                           "message,created_time,from,permalink_url,"
                           "comments.limit(20){message,created_time,from,permalink_url}"
                           "},shares"):
                pages += 1
                posts.extend(page)
            self.count(self.ID, calls=pages)
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"facebook · feed failed ({e})")
            return
        self.log(f"facebook · {len(posts)} posts across {pages} page(s)")
        for p in posts:
            pid = p.get("id")
            if p.get("message"):
                metrics = {
                    "likes": (p.get("likes") or {}).get("summary", {}).get("total_count"),
                    "comments": (p.get("comments") or {}).get("summary", {}).get("total_count"),
                    "shares": (p.get("shares") or {}).get("count"),
                }
                # Graph API doesn't expose a playable video file URL for a Page
                # post (DRM/policy) -- full_picture is a real thumbnail for
                # both photo and video posts; a video is tagged so the UI can
                # show a play badge that links out to watch it on Facebook.
                attachment_type = next(
                    (a.get("media_type") for a in (p.get("attachments") or {}).get("data") or []),
                    None)
                media = None
                if p.get("full_picture"):
                    media = {"type": "video" if attachment_type == "video" else "photo",
                             "image": p["full_picture"]}
                yield self._emit(f"fb:{pid}", p.get("permalink_url"),
                                 (p.get("from") or {}).get("name"),
                                 p.get("created_time"), p.get("message"), "post", metrics,
                                 parent_id=None, media=media)
            for cmt in ((p.get("comments") or {}).get("data") or []):
                cid = cmt.get("id")
                if cmt.get("message"):
                    yield self._emit(
                        f"fb:{cid}", cmt.get("permalink_url") or p.get("permalink_url"),
                        (cmt.get("from") or {}).get("name"),
                        cmt.get("created_time"), cmt.get("message"), "comment",
                        parent_id=f"fb:{pid}")
                for reply in ((cmt.get("comments") or {}).get("data") or []):
                    rid = reply.get("id")
                    if not reply.get("message"):
                        continue
                    yield self._emit(
                        f"fb:{rid}", reply.get("permalink_url") or p.get("permalink_url"),
                        (reply.get("from") or {}).get("name"),
                        reply.get("created_time"), reply.get("message"), "reply",
                        parent_id=f"fb:{cid}")


class MetaInstagram(MetaBase):
    ID = "meta_instagram"
    SURFACE_OUTLET = "Instagram"

    def fetch(self, terms):
        try:
            media, pages = [], 0
            for page in self._paginate(
                    f"{self.k['META_IG_USER_ID']}/media", limit=50,
                    fields="caption,permalink,timestamp,like_count,comments_count,"
                           "media_type,media_url,thumbnail_url,"
                           "comments.limit(50){text,timestamp,username,"
                           "replies{text,timestamp,username}}"):
                pages += 1
                media.extend(page)
            self.count(self.ID, calls=pages)
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"instagram · media failed ({e})")
            return
        self.log(f"instagram · {len(media)} media across {pages} page(s)")
        for m in media:
            mid = m.get("id")
            if m.get("caption"):
                # IG media carries no per-item "posted by" name (it's always
                # the connected account) -- leave author unset rather than
                # fabricate a brand name that may belong to a different tenant.
                metrics = {"likes": m.get("like_count"), "comments": m.get("comments_count")}
                # Unlike Facebook, IG's Graph API does expose a real, directly
                # playable file URL -- media_url is a video file for VIDEO/
                # REELS (thumbnail_url is its poster) and the image itself for
                # IMAGE/CAROUSEL_ALBUM.
                media_type = (m.get("media_type") or "").upper()
                media_info = None
                if media_type == "VIDEO":
                    media_info = {"type": "video", "video": m.get("media_url"),
                                  "image": m.get("thumbnail_url")}
                elif m.get("media_url"):
                    media_info = {"type": "photo", "image": m.get("media_url")}
                yield self._emit(f"ig:{mid}", m.get("permalink"), None,
                                 m.get("timestamp"), m.get("caption"), "post", metrics,
                                 parent_id=None, media=media_info)
            for cmt in ((m.get("comments") or {}).get("data") or []):
                cid = cmt.get("id")
                if cmt.get("text"):
                    yield self._emit(f"ig:{cid}", m.get("permalink"),
                                     cmt.get("username"), cmt.get("timestamp"),
                                     cmt.get("text"), "comment", parent_id=f"ig:{mid}")
                for reply in ((cmt.get("replies") or {}).get("data") or []):
                    rid = reply.get("id")
                    if not reply.get("text"):
                        continue
                    yield self._emit(f"ig:{rid}", m.get("permalink"),
                                     reply.get("username"), reply.get("timestamp"),
                                     reply.get("text"), "reply", parent_id=f"ig:{cid}")
