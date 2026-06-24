#!/usr/bin/env python3
"""
mediabank.py — the dataset + the matcher (stages 3 & 4 of Syng).

STAGE 3 (dataset): a bank of media items, each tagged with the moods it represents
and an energy (0-1) for the strength of that emotion. Today every item is a YouTube
song (songbank.json). The schema is deliberately open: each item carries a `kind`
(song | meme | clip | image | …) and a `source` (youtube | spotify | local | …), so
tomorrow the same bank can hold audio, video, memes, or pictures.

STAGE 4 (matcher): given a mood verdict (mood + intensity), find the item that best
represents it and hand back a playable link. The link is built by a PROVIDER keyed on
the item's `source` — register a new provider and a new media source plays itself.

Deterministic: the same situation maps to the same item until the bank changes, so a
result has ONE anthem (tiebroken on a caller-supplied seed key).
"""

import hashlib
import json
import os
import urllib.parse

BANK_PATH = os.path.join(os.path.dirname(__file__), "songbank.json")


# ---------------------------------------------------------------------------
# Providers — turn a dataset item into a playable link, by `source`.
# This registry is the expansion point for new media: add spotify/local/imgur/…
# ---------------------------------------------------------------------------

def _youtube_link(item):
    if item.get("yt"):
        return f"https://www.youtube.com/watch?v={item['yt']}"
    q = urllib.parse.quote_plus(f"{item.get('title', '')} {item.get('artist', '')}".strip())
    return f"https://www.youtube.com/results?search_query={q}"


PROVIDERS = {"youtube": _youtube_link}


def register_provider(source, fn):
    """Teach the bank how to build a play-link for a new media `source`."""
    PROVIDERS[source] = fn


def play_link(item):
    src = item.get("source", "youtube")
    return PROVIDERS.get(src, _youtube_link)(item)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

def load_bank(path=BANK_PATH):
    with open(path) as f:
        items = json.load(f)["songs"]
    for it in items:
        it.setdefault("kind", "song")       # future: meme | clip | image | gif | quote
        it.setdefault("source", "youtube")  # future: spotify | local | imgur | vimeo
    return items


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------

def match(verdict, kind=None, lang=None, seed_key="", bank=None):
    """Return (winner, runners_up) — the items that best fit this mood + strength.

    kind:     restrict to one media kind (e.g. "song"); falls back if it empties out.
    lang:     optional language preference; falls back rather than returning nothing.
    seed_key: deterministic tiebreak — same key -> same pick until the bank changes.
    """
    items = bank if bank is not None else load_bank()
    mood = verdict["mood"]
    intensity = float(verdict.get("intensity", 0.5))

    cands = [s for s in items if mood in s["moods"]]
    if kind:
        cands = [s for s in cands if s.get("kind", "song") == kind] or cands
    if lang:
        cands = [s for s in cands if s.get("lang") == lang] or cands
    if not cands:
        cands = items  # degenerate fallback — never end up media-less

    seed = int(hashlib.sha256(seed_key.encode()).hexdigest(), 16)

    def score(s):
        # energy proximity matters, but jitter is wide enough that one item can't
        # camp on a whole mood (the Sixteen Tons problem from the songbank days).
        jitter = (int(hashlib.sha256((s["title"] + str(seed)).encode()).hexdigest(), 16)
                  % 1000) / 4000.0
        primary = 1.0 if s["moods"][0] == mood else 0.9  # prefer items whose FIRST mood matches
        return primary - abs(s.get("energy", 0.5) - intensity) + jitter

    ranked = sorted(cands, key=score, reverse=True)
    return ranked[0], ranked[1:3]
