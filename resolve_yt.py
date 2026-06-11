#!/usr/bin/env python3
"""
resolve_yt.py — bake a playable YouTube video id into each songbank entry.

YouTube discontinued the listType=search embed, so the web app embeds a real
video id instead. This script (run locally, once per songbank change):
  1. searches YouTube for "title artist"
  2. takes the first few candidate video ids
  3. keeps the first one whose oEmbed lookup succeeds (a decent proxy for
     "public and embeddable")
  4. writes it back as the song's "yt" field, with the resolved title in
     "yt_title" so a human can eyeball the matches

Songs that already have "yt" are skipped — curate by hand freely.
"""

import json
import re
import subprocess
import sys
import time
import urllib.parse

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
BANK = "songbank.json"


def http_get(url):
    out = subprocess.run(["curl", "-sS", "--fail-with-body", "--compressed",
                          "-m", "20", "-A", UA, url],
                         capture_output=True, timeout=25)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.decode()[:160])
    return out.stdout.decode("utf-8", "replace")


def search_ids(query, n=5):
    html = http_get("https://www.youtube.com/results?search_query="
                    + urllib.parse.quote_plus(query))
    ids, seen = [], set()
    for vid in re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html):
        if vid not in seen:
            seen.add(vid)
            ids.append(vid)
        if len(ids) >= n:
            break
    return ids


def oembed_title(vid):
    try:
        j = json.loads(http_get(
            "https://www.youtube.com/oembed?format=json&url="
            + urllib.parse.quote_plus(f"https://www.youtube.com/watch?v={vid}")))
        return j.get("title")
    except Exception:
        return None


def main():
    with open(BANK) as f:
        bank = json.load(f)
    songs = bank["songs"]
    todo = [s for s in songs if not s.get("yt")]
    print(f"{len(todo)} of {len(songs)} songs need a video id")
    misses = []
    for i, s in enumerate(todo, 1):
        q = f"{s['title']} {s['artist']}"
        try:
            for vid in search_ids(q):
                title = oembed_title(vid)
                if title:
                    s["yt"], s["yt_title"] = vid, title
                    break
            else:
                misses.append(s["title"])
        except Exception as e:
            misses.append(f"{s['title']} ({e})")
        print(f"[{i}/{len(todo)}] {s['title']!r:45} -> {s.get('yt','MISS')} {s.get('yt_title','')[:60]}")
        time.sleep(0.4)  # be polite
        if i % 20 == 0:
            with open(BANK, "w") as f:   # checkpoint
                json.dump(bank, f, ensure_ascii=False, indent=1)
    with open(BANK, "w") as f:
        json.dump(bank, f, ensure_ascii=False, indent=1)
    print(f"\ndone. misses: {misses or 'none'}")
    return 0 if not misses else 1


if __name__ == "__main__":
    sys.exit(main())
