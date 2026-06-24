#!/usr/bin/env python3
"""
perceive.py — stage 1: understand the situation pointed at the jukebox.

Whatever you point Syng at — a line of text, a pasted tweet, a screenshot — has to
become a plain-language SITUATION before the emotion scorer (vibe.py) can read it.
This module is the input layer that does that, and only that.

It's a registry: each input kind has a handler that returns
    {"text": <situation in words>, "input_kind": <kind>, "meta": {...}}
Add a handler, support a new input kind. Today: text, tweet, image (online vision).
Tomorrow: a URL to scrape, an audio clip to transcribe, a PDF — same shape out.
"""

import re

HANDLERS = {}


def handler(*kinds):
    def deco(fn):
        for k in kinds:
            HANDLERS[k] = fn
        return fn
    return deco


@handler("text", "tweet", "conversation", "headline")
def _read_text(source, offline):
    txt = (source.get("text") or "").strip()
    if not txt:
        raise ValueError("no text to read")
    # tweets come with URLs/handle noise that adds nothing to the mood — trim lightly
    cleaned = re.sub(r"https?://\S+", "", txt).strip() if source.get("type") == "tweet" else txt
    return {"text": cleaned or txt, "input_kind": source.get("type", "text"), "meta": {}}


@handler("image")
def _read_image(source, offline):
    if offline:
        raise ValueError("reading an image needs the online oracle (vision) — "
                         "the free offline path is text-only")
    data = source.get("data")
    if not data:
        raise ValueError("no image data (expected base64 in source.data)")
    media_type = source.get("media_type", "image/png")

    import anthropic
    from dotenv import load_dotenv
    load_dotenv()
    from vibe import MODEL  # share the model id with the scorer

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media_type, "data": data}},
                {"type": "text",
                 "text": "In 2-3 sentences, describe what's happening in this image and "
                         "its emotional tenor. Just the description — no preamble."},
            ],
        }],
    )
    desc = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not desc:
        raise ValueError("couldn't read the image")
    return {"text": desc, "input_kind": "image", "meta": {"caption": desc}}


def perceive(source, offline=False):
    """source: a string (treated as text), or {"type": ..., ...}. Returns a situation."""
    if isinstance(source, str):
        source = {"type": "text", "text": source}
    kind = source.get("type", "text")
    fn = HANDLERS.get(kind)
    if fn is None:
        raise ValueError(f"don't know how to read input of type '{kind}' "
                         f"(have: {', '.join(sorted(HANDLERS))})")
    return fn(source, offline)
