#!/usr/bin/env python3
"""
syng.py — Syng: "there's a song for this". The orchestrator.

Wires the four modular stages into one pipeline. Each stage is swappable; this file
only knows the seams between them, not their internals.

    perceive   →   vibe        →   mediabank
    (understand    (score the      (match a media item
     the input)     emotion)        + a link to play)

Input can be text, a tweet, or an image (today); output is a YouTube link (today).
Both ends expand by registering handlers (perceive) / providers (mediabank) — this
orchestrator doesn't change when they do.
"""

import mediabank
import perceive
import vibe


def syng(source, offline=True, lang=None, kind="song", verbose=False):
    """source: str or {"type": ..., ...}. Returns the whole pipeline's output."""
    situation = perceive.perceive(source, offline=offline)
    verdict = vibe.score(situation["text"], offline=offline, verbose=verbose)
    winner, runners = mediabank.match(
        verdict, kind=kind, lang=lang,
        # deterministic: the same situation maps to the same song until the bank changes
        seed_key=situation["text"][:200],
    )
    return {
        "situation": situation,
        "verdict": verdict,
        "match": winner,
        "runners": runners,
    }


if __name__ == "__main__":
    import json
    import sys

    offline = "--offline" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    text = " ".join(args) if args else sys.stdin.read()
    result = syng(text, offline=offline, verbose=True)
    v, song = result["verdict"], result["match"]
    print(f"\n  mood: {v['mood']}  (intensity {v['intensity']:.2f})")
    print(f"  read: {v.get('read', '')}")
    print(f"\n  🎵 «{song['title']}» — {song['artist']} ({song['era']})")
    print(f"     {song['why_it_fits']}")
    print(f"     ▶ {mediabank.play_link(song)}\n")
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2, ensure_ascii=False))
