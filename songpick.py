#!/usr/bin/env python3
"""
songpick.py — the song-specific face of the matcher.

The general matcher now lives in mediabank.py (it works over any media kind and
any play-link provider). This module is the thin, song-flavoured wrapper the
financial-symphony path has always used: same quarter -> same song, deterministic
on company+quarter. Kept so app.py's /judge flow is unchanged.
"""

import subprocess

import mediabank

BANK_PATH = mediabank.BANK_PATH
load_bank = mediabank.load_bank


def youtube_url(song):
    return mediabank.play_link(song)


def pick(verdict, company="", quarter="", lang=None):
    """Returns (winner, runners_up). Deterministic on company+quarter."""
    return mediabank.match(verdict, kind="song", lang=lang,
                           seed_key=f"{company}|{quarter}")


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
