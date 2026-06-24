#!/usr/bin/env python3
"""
vibe.py — Syng's emotion scorer (stage 2) — the judge, generalised.

The Financial Symphony Generator judges a quarter into one of seven moods and
hands that mood to the songbank. It turns out those seven moods aren't really
financial at all — they're the whole emotional weather of human affairs:

    triumph · steady · grind · turnaround_hope · distress · illusion · shock

So this module does the same job as judge.py, but for ANY situation: a tweet,
a headline, an overheard line, a corporate fiasco, a political own-goal. Text
goes in, a mood comes out, and the songbank (unchanged) supplies the anthem.

Online mode: Claude (Opus 4.8) + web search, for when the text references a real
event whose mood you can only judge with context. Offline mode: deterministic
keyword rules, no API, no network — free, instant, and pleasingly stupid.

The verdict dict it returns is shaped to drop straight into songpick.pick().
"""

import json
import os
import re
import sys

from judge import MOODS  # single source of truth for the mood vocabulary

# Opus 4.8 for the general classifier: the user has moved off Fable, and a mood
# read of free text doesn't need Fable's price tag. judge.py keeps Fable for the
# heavier financial reasoning.
MODEL = "claude-opus-4-8"

VERDICT_SCHEMA_HINT = """{
  "mood": "one of: triumph | steady | grind | turnaround_hope | distress | illusion | shock",
  "intensity": 0.0,
  "read": "one-line read of the situation's emotional truth — wry, specific",
  "why": "why this mood (and so this kind of song) fits",
  "evidence": ["concrete observations from the text or from search"]
}"""

SYSTEM_PROMPT = """You are the mood oracle behind a jukebox. You are handed a fragment of
the human comedy — a tweet, a news headline, a snatch of conversation, a corporate or
political story — and your single job is to name its emotional weather, so the jukebox
can pick the right song.

Pick EXACTLY ONE mood from this vocabulary. They were forged to judge company results,
but they generalise to anything:

- triumph: a genuine, earned win. The underdog delivered; the thing actually worked.
- steady: calm continuation. Compounding quietly, no drama, the centre holds.
- grind: the slog. Treading water, fighting through, neither winning nor losing.
- turnaround_hope: an inflection after a bad stretch — real but unproven. The comeback's
  first act, the bottom that might be in.
- distress: real deterioration. Things are genuinely going wrong and getting worse.
- illusion: looks great on the surface, hollow underneath. Spin, hype, optics, a beat
  built on nothing — the gross-revenue illusion, but for life. The press release that
  the cash flow (or the facts) won't honour.
- shock: a sudden severe lurch nobody saw coming. The bombshell, the scandal, the
  guidance bomb, the plot twist.

Judge the SITUATION, not the speaker's spin. If a tweet is triumphant in tone but the
underlying reality is hollow, that's `illusion`, not `triumph` — the same discipline a
good analyst applies to a headline beat. Apply the gross-revenue-illusion instinct
everywhere: separate the announcement from the substance.

Use web search ONLY if the text points at a specific real-world event whose mood you
genuinely can't judge from the words alone (e.g. "the result is in" — what result?).
For a self-contained tweet or a general situation, don't search; just read it.

intensity (0-1) = how strongly the mood applies — how loud the song should be.

End your response with EXACTLY ONE fenced json block matching this schema, and no other
fenced json anywhere:
```json
""" + VERDICT_SCHEMA_HINT + """
```"""


# ---------------------------------------------------------------------------
# Online classifier — Opus 4.8 + web search
# ---------------------------------------------------------------------------

def classify_online(text, verbose=True):
    import anthropic
    from dotenv import load_dotenv
    load_dotenv()

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env/.env

    user_msg = ("Name the mood of this. Search only if it points at a real event you "
                "can't judge from the words.\n\n---\n" + text.strip() + "\n---")
    messages = [{"role": "user", "content": user_msg}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 4}]

    response = None
    for _ in range(5):  # pause_turn continuation cap for the server-side search loop
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            thinking={"type": "adaptive"},  # Opus 4.8: adaptive only, no budget_tokens
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )
        if response.stop_reason != "pause_turn":
            break
        messages = [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": response.content},
        ]

    out = "\n".join(b.text for b in response.content if b.type == "text")
    if verbose:
        prose = re.sub(r"```json.*?```", "", out, flags=re.S).strip()
        if prose:
            print("\n--- Oracle's reading " + "-" * 40)
            print(prose[:1500])
            print("-" * 62)

    fences = re.findall(r"```json\s*(.*?)```", out, flags=re.S)
    if not fences:
        raise RuntimeError("Oracle returned no JSON verdict. Raw tail:\n" + out[-800:])
    return normalize(json.loads(fences[-1]))


# ---------------------------------------------------------------------------
# Offline classifier — deterministic keyword rules (no API)
# ---------------------------------------------------------------------------

# Each mood carries a lexicon of tells. Crude but free; the online oracle is where
# the real judgement lives. Order of MOOD_CUES doubles as tie-break priority:
# the louder, more decisive moods win ties over the quieter ones.
MOOD_CUES = {
    "shock": [
        "shock", "shocking", "shocked", "stunned", "sudden", "suddenly", "bombshell",
        "scandal", "breaking", "out of nowhere", "resigned", "resign", "fired", "sacked",
        "arrested", "exposed", "leaked", "leak", "plot twist", "unexpected", "jaw-drop",
        "fraud", "raid", "bankrupt", "collapse overnight", "wiped out", "blindsided",
    ],
    "illusion": [
        "hype", "hyped", "spin", "smoke and mirrors", "allegedly", "claims", "on paper",
        "propaganda", "vaporware", "overhyped", "too good to be true", "facade", "optics",
        "narrative", "pr stunt", "publicity stunt", "greenwash", "papering over", "facade",
        "looks good but", "supposedly", "marketing gimmick", "all talk", "buzzword",
        "cooking the books", "window dressing", "paper profit",
    ],
    "triumph": [
        "won", "win", "victory", "champion", "triumph", "smashed", "crushed it", "record",
        "breakthrough", "landmark", "historic", "blowout", "soared", "surged", "best ever",
        "gold medal", "nailed it", "nailed", "aced", "milestone", "knocked it out",
        "dominated", "runaway success", "smash hit", "killing it", "we did it",
        "shipped it", "pulled it off", "launched", "buzzing", "delivered",
    ],
    "distress": [
        "crisis", "collapse", "plunge", "plunged", "losses", "loss", "decline", "failing",
        "trouble", "layoff", "layoffs", "debt", "bleeding", "sinking", "deteriorat",
        "worse", "falling apart", "grim", "bleak", "meltdown", "downward spiral",
        "struggling badly", "going under", "in the red", "default",
    ],
    "turnaround_hope": [
        "comeback", "recovery", "recovering", "turnaround", "rebound", "bottomed", "hope",
        "hopeful", "green shoots", "signs of", "improving", "on the mend", "second wind",
        "rebuilding", "fresh start", "light at the end", "stabilising", "stabilizing",
        "first signs", "starting to", "early days but", "inflection",
    ],
    "grind": [
        "grind", "slog", "struggle", "treading water", "flat", "stagnant", "plodding",
        "burnout", "exhausted", "monday", "deadline", "overtime", "no movement", "stuck",
        "same old", "hard yards", "uphill", "wearing thin", "drudgery", "grinding",
        "another day", "keeping the lights on",
    ],
    "steady": [
        "steady", "stable", "as expected", "on track", "consistent", "business as usual",
        "holding", "unchanged", "reliable", "calm", "routine", "maintained", "in line",
        "no surprises", "ticking along", "solid quarter", "according to plan",
    ],
}

_POS = ("great", "good", "love", "happy", "excited", "amazing", "proud", "winning")
_NEG = ("bad", "awful", "hate", "sad", "angry", "worried", "terrible", "losing", "fear")


def classify_offline(text):
    low = text.lower()
    scores = {m: 0 for m in MOOD_CUES}
    hits = {m: [] for m in MOOD_CUES}
    for mood, cues in MOOD_CUES.items():
        for cue in cues:
            if cue in low:
                scores[mood] += 1
                hits[mood].append(cue)

    best = max(scores, key=lambda m: scores[m]) if any(scores.values()) else None
    if best is None or scores[best] == 0:
        # no tells fired — fall back to coarse sentiment
        pos = sum(w in low for w in _POS)
        neg = sum(w in low for w in _NEG)
        best = "steady" if pos >= neg else "grind"
        matched = []
    else:
        # break ties by MOOD_CUES order (louder moods first)
        top = max(scores.values())
        for mood in MOOD_CUES:
            if scores[mood] == top:
                best = mood
                break
        matched = hits[best]

    bangs = low.count("!")
    letters = [c for c in text if c.isalpha()]
    caps_ratio = sum(c.isupper() for c in letters) / len(letters) if letters else 0
    intensity = 0.45 + 0.12 * scores[best] + 0.05 * min(bangs, 4) + 0.25 * (caps_ratio > 0.4)
    intensity = round(min(1.0, intensity), 2)

    read = f"Reads as {best.replace('_', ' ')} (offline rules — no context fetched)."
    evidence = ([f"matched: {', '.join(matched[:5])}"] if matched
                else ["no strong keywords — judged on sentiment"])
    return normalize({
        "mood": best,
        "intensity": intensity,
        "read": read,
        "why": f"Offline ruling: the words land as {best.replace('_', ' ')}.",
        "evidence": evidence,
    })


# ---------------------------------------------------------------------------

def normalize(v):
    """Defend against schema drift from the model."""
    if v.get("mood") not in MOODS:
        v["mood"] = "grind"
    v["intensity"] = float(max(0.0, min(1.0, v.get("intensity", 0.5))))
    v.setdefault("read", "")
    v.setdefault("why", "")
    ev = v.get("evidence") or []
    v["evidence"] = ev if isinstance(ev, list) else [str(ev)]
    return v


def classify(text, offline=False, verbose=True):
    if not text or not text.strip():
        raise ValueError("nothing to judge — give me some text")
    if offline:
        return classify_offline(text)
    return classify_online(text, verbose=verbose)


# the pipeline calls this stage "scoring the emotion"; classify is the same thing
score = classify


if __name__ == "__main__":
    offline = "--offline" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    text = " ".join(args) if args else sys.stdin.read()
    print(json.dumps(classify(text, offline=offline), indent=2, ensure_ascii=False))
