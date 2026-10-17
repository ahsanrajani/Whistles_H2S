"""63-bit Charikar SimHash for near-duplicate detection across sources (P2.1).

SimHash over word 3-shingles: two texts are near-duplicates when the Hamming
distance of their hashes is small. ``collection/dedupe.py`` uses it to fold a
story that a *different* source re-reported almost verbatim — the job the old
exact-URL pass did wrongly, folding anything that merely shared a URL.

63 bits, not 64, so the value always fits a signed Postgres ``BIGINT``; the
lost bit is immaterial to near-dup detection.
"""
import hashlib
import re
from collections import Counter

BITS = 63
NEAR_DUP_MAX_DISTANCE = 8
# SimHash is a whole-document signal: on a multi-sentence article a small edit
# moves ~3-5 bits and an unrelated piece ~25, a clean gap. On a tweet or a
# one-line review the vote is too noisy to separate the two, so below this many
# word tokens we return 0 ("no hash") and lean on content_hash for exact dups.
MIN_TOKENS = 50
_TOKEN = re.compile(r"\w+")


def _features(text: str) -> Counter:
    """Frequency-weighted uni/bi/tri-grams. Overlapping n-gram widths give the
    hash enough features to stay stable under a small edit — a single-word
    change in a ~50-word paragraph moves only a handful of bits."""
    tokens = _TOKEN.findall((text or "").lower())
    if len(tokens) < MIN_TOKENS:
        return Counter()
    feats: Counter = Counter()
    n = len(tokens)
    for i, tok in enumerate(tokens):
        feats[tok] += 1
        if i + 1 < n:
            feats[tok + " " + tokens[i + 1]] += 1
        if i + 2 < n:
            feats[" ".join(tokens[i:i + 3])] += 1
    return feats


def simhash(text: str) -> int:
    """The SimHash of ``text`` as a non-negative 63-bit int. ``0`` for text with
    no word tokens (treated as "no hash" by the dedupe pass)."""
    feats = _features(text)
    if not feats:
        return 0
    vector = [0] * BITS
    for feat, weight in feats.items():
        h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
        for bit in range(BITS):
            vector[bit] += weight if (h >> bit) & 1 else -weight
    out = 0
    for bit in range(BITS):
        if vector[bit] > 0:
            out |= 1 << bit
    return out


def hamming(a: int, b: int) -> int:
    return ((a or 0) ^ (b or 0)).bit_count()


def bands(h: int, n: int = 3):
    """``n`` roughly-equal slices of the hash. Two items that share any slice
    are LSH candidates for a full Hamming comparison. With ``n=3`` over 63 bits
    each band is 21 bits, and any pair within Hamming distance 2 shares a band
    (pigeonhole); distance 3 is caught most of the time — good enough, and the
    ``content_hash`` / ``norm_title`` passes cover the verbatim cases anyway."""
    width = BITS // n
    mask = (1 << width) - 1
    return tuple((h >> (width * i)) & mask for i in range(n))
