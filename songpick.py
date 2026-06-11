#!/usr/bin/env python3
"""
songpick.py — Renderer B: match the verdict to a song and play it via YouTube.

Same quarter -> same song (deterministic tiebreak on company+quarter), so a
result has ONE anthem until the songbank changes.
"""

import hashlib
import json
import os
import subprocess
import urllib.parse

BANK_PATH = os.path.join(os.path.dirname(__file__), "songbank.json")


def load_bank():
    with open(BANK_PATH) as f:
        return json.load(f)["songs"]


def youtube_url(song):
    if song.get("yt"):
        return f"https://www.youtube.com/watch?v={song['yt']}"
    q = urllib.parse.quote_plus(f"{song['title']} {song['artist']}")
    return f"https://www.youtube.com/results?search_query={q}"


def pick(verdict, company="", quarter="", lang=None):
    """Returns (winner, runners_up). lang: optionally 'hi' or 'en' to filter."""
    bank = load_bank()
    mood, intensity = verdict["mood"], verdict["intensity"]

    candidates = [s for s in bank if mood in s["moods"]]
    if lang:
        filtered = [s for s in candidates if s["lang"] == lang]
        candidates = filtered or candidates  # never end up song-less
    if not candidates:
        candidates = bank  # degenerate fallback

    seed = int(hashlib.sha256(f"{company}|{quarter}".encode()).hexdigest(), 16)

    def score(s):
        # energy proximity matters but jitter is wide enough that one song
        # can't camp on a whole mood (Sixteen Tons won 7 of 13 grinds at 0.1)
        jitter = (int(hashlib.sha256((s["title"] + str(seed)).encode()).hexdigest(), 16)
                  % 1000) / 4000.0
        primary = 1.0 if s["moods"][0] == mood else 0.9  # prefer songs whose FIRST mood matches
        return primary - abs(s["energy"] - intensity) + jitter

    ranked = sorted(candidates, key=score, reverse=True)
    return ranked[0], ranked[1:3]


def announce(song, verdict, runners_up=()):
    lines = [
        "",
        "🎵 This quarter's anthem:",
        f"   «{song['title']}» — {song['artist']} ({song['era']})",
        f"   Why: {song['why_it_fits']}",
        f"   Mood: {verdict['mood']} (intensity {verdict['intensity']:.2f}) | Grade: {verdict['grade']}",
    ]
    if runners_up:
        lines.append("   Also considered: " +
                     "; ".join(f"«{s['title']}» ({s['artist']})" for s in runners_up))
    lines.append(f"   ▶ {youtube_url(song)}")
    return "\n".join(lines)


def play(song):
    subprocess.run(["open", youtube_url(song)], check=False)
