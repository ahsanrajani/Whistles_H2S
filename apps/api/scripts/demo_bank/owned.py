"""The brand's own channels: posts with real engagement metrics, the comments
under them (including a scam wave a few weeks ago and a smaller one now), and
the engagement warehouse (via the same mock providers the product ships)."""
import math

from core import owned_analytics

from . import corpus as C
from .base import NOW, Seed, stamp

# platform -> (source, metric keys, typical engagement, comment-capable)
PLATFORMS = {
    "facebook": ("meta_facebook", ("likes", "comments", "shares"), 90, True),
    "instagram": ("meta_instagram", ("likes", "comments"), 160, True),
    "linkedin": ("brightdata_linkedin_posts", ("likes", "comments", "shares"), 50, False),
    "youtube": ("youtube_owned_videos", ("views", "likes", "comments"), 700, False),
    "x": ("x_owned_posts", ("likes", "reposts", "replies", "quotes"), 45, False),
}
_WAVES = ((14, 19, 0.36), (5, 10, 0.02), (0, 4, 0.10))        # (from day, to day, share of comments that are scams)
_REPEAT_SCAMMERS = [f"official_support_{k}" for k in range(1, 3)]


def _boost(hour: int, weekday: int) -> float:
    return (1.8 if 18 <= hour <= 23 else 0.7 if 6 <= hour < 12 else 1.0) * (1.3 if weekday in (3, 4) else 1.0)


def posts(sd: Seed) -> dict[str, list[tuple[str, float]]]:
    """Insert owned posts; returns {platform: [(external_id, days_ago), ...]}."""
    rng, out = sd.rng, {}
    for platform, (source, keys, typical, _c) in PLATFORMS.items():
        out[platform] = []
        for i in range(8):
            days = 1.2 if i == 0 and platform == "facebook" else 3 + i * 10 + rng.random() * 3
            hour = rng.choice([9, 11, 13, 20, 21, 22])
            weekday = int((NOW.weekday() - int(days)) % 7)
            title, _topic = C.POSTS[(i + len(platform)) % len(C.POSTS)]
            level = typical * _boost(hour, weekday) * math.exp(rng.gauss(0, 0.35))
            if i == 0 and platform == "facebook":
                level *= 3.0                       # the popular post scammers work
            metrics = {k: int(level * f) for k, f in zip(keys, (1.0, 0.12, 0.08, 0.04)[:len(keys)])}
            if platform == "youtube":
                metrics = {"views": int(level * 9), "likes": int(level * 0.6), "comments": int(level * 0.05)}
            ext = sd.item(source=source, body=title, when=stamp(days, hour), kind="post", outlet=platform.title(),
                          author="Lumora Bank", raw={"metrics": metrics}, label=f"posts:{platform}")
            out[platform].append((ext, days))
    return out


def comments(sd: Seed, posted: dict) -> None:
    """Comments under the Facebook and Instagram posts. Scam share follows the
    wave schedule, so before/after comparisons around a warning post mean something."""
    rng = sd.rng
    for platform in ("facebook", "instagram"):
        source = PLATFORMS[platform][0]
        plist = sorted(posted[platform], key=lambda p: p[1])         # newest first
        carry = 0.0                       # scam comments follow a running quota, so the rate never depends on the RNG
        for day in range(0, 42):
            wave = next((p for lo, hi, p in _WAVES if lo <= day <= hi), 0.02)
            hot = platform == "facebook" and day <= 2
            total = rng.randint(6, 9) if hot else rng.randint(2, 5)
            carry += total * (0.18 if hot else wave)
            quota, carry = int(carry), carry - int(carry)
            for index in range(total):
                parent = next((e for e, d in plist if d >= day), None)
                if parent is None:
                    break
                when = stamp(day + rng.random() * 0.6, rng.randint(8, 23), rng.randint(0, 59))
                if index < quota:
                    who = rng.choice(_REPEAT_SCAMMERS)
                    sd.item(source=source, body=rng.choice(C.SCAM_COMMENTS), when=when, brands=[C.FOCUS], kind="comment",
                            author=who, outlet=platform.title(), sentiment="neu", category="fraud",
                            raw={"parent_id": parent, "actor_hash": f"sc{who.rsplit('_', 1)[1]}"}, label=f"comments:{platform}")
                    continue
                neg = rng.random() < 0.3
                topic = rng.choice(["app", "cards", "branch", "payments", "service"])
                body = (C.T[(topic, "neg")][rng.randrange(len(C.T[(topic, "neg")]))].format(
                    b=C.FOCUS, n=rng.randint(2, 6), amt="Rs 25,000", city=rng.choice(C.CITIES))
                    if neg else rng.choice(C.CLEAN_COMMENTS))
                author = sd.handle()
                sd.item(source=source, body=body, when=when, brands=[C.FOCUS], kind="comment", author=author,
                        outlet=platform.title(), sentiment="neg" if neg else rng.choice(["pos", "pos", "neu"]),
                        category="complaint" if neg else rng.choice(["praise", "question"]),
                        raw={"parent_id": parent, "actor_hash": f"u-{author}"}, label=f"comments:{platform}")


def engagement_warehouse(sd: Seed) -> dict:
    """90 days of account-level metrics via the product's own mock providers."""
    out = owned_analytics.ingest(sd.s, sd.ws, days=90, keys={})
    sd.bump("metric_fact", out.get("total", 0) if isinstance(out, dict) else 0)
    return out


_OTHER_COMMENTS = {
    "linkedin": ["Congratulations to the team on the launch.", "Useful explainer, thank you for sharing.",
                 "Would love to see the SME offer details.", "Great to see a bank explaining fees this clearly."],
    "youtube": ["Clear walkthrough, the new login screen is easier.", "Can you make a video on the QR payment limits?",
                "The sound is low but the content is helpful.", "Subscribed. More banking tips for seniors please."],
    "x": ["Thanks for the quick clarification.", "Any update on the app outage?", "Good initiative, hope it reaches branches too.",
          "Please share the helpline number again."],
}


def other_platform_comments(sd: Seed, posted: dict) -> None:
    """A few replies/comments under every non-Meta post so no post looks untouched."""
    rng = sd.rng
    for platform, bodies in _OTHER_COMMENTS.items():
        source = PLATFORMS[platform][0]
        for ext, days in posted[platform]:
            for _ in range(rng.randint(1, 4)):
                author = sd.handle()
                neg = rng.random() < 0.2
                body = (rng.choice(["Still facing the login problem after the update.", "Waited a long time for support, no reply yet."])
                        if neg else rng.choice(bodies))
                sd.item(source=source, body=body, when=stamp(max(0.0, days - rng.random() * 2), rng.randint(8, 23)), brands=[C.FOCUS],
                        kind="comment", author=author, outlet=platform.title(), sentiment="neg" if neg else rng.choice(["pos", "neu"]),
                        category="complaint" if neg else rng.choice(["praise", "question"]),
                        raw={"parent_id": ext, "actor_hash": f"u-{author}"}, label=f"comments:{platform}")
