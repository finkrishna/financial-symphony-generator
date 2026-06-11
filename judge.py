#!/usr/bin/env python3
"""
judge.py — the analytical core of the Financial Symphony Generator.

Takes a quarterly result JSON, judges it the way a disciplined analyst would —
vs the company's own past, vs competition, vs market expectations — and returns
a structured verdict that drives the music renderers.

Online mode: Claude (Fable 5) + web search fetches peer/market context itself.
Offline mode (--offline): deterministic rules, no API, no network.
"""

import json
import os
import re
import sys

MOODS = ("triumph", "steady", "grind", "turnaround_hope", "distress", "illusion", "shock")

VERDICT_SCHEMA_HINT = """{
  "mood": "one of: triumph | steady | grind | turnaround_hope | distress | illusion | shock",
  "intensity": 0.0,
  "grade": "A+ | A | B+ | B | C+ | C | D | F",
  "scores": {
    "growth_vs_past": 0, "vs_peers": 0, "vs_expectations": 0,
    "margin_quality": 0, "cash_quality": 0, "balance_sheet": 0
  },
  "headline": "one-line verdict",
  "key_evidence": ["specific numbers, incl. peer results found via search"],
  "red_flags": ["..."],
  "music_brief": "one paragraph directing how this quarter should SOUND"
}"""

SYSTEM_PROMPT = """You are a buy-side equity analyst judging a quarterly result.
You apply these non-negotiable research disciplines:

1. GROSS-REVENUE ILLUSION: in payments/fintech/aggregators, decompose gross
   reported revenue to net take-rate revenue before judging growth. A headline
   beat built on gross-revenue optics with poor cash conversion is an ILLUSION.
2. ONE-OFF MIRAGE: headline profit driven by one-time items (tax credits,
   asset sales, write-backs) is NOT performance. Never grade up on non-recurring items.
3. TROUGH != THESIS: confirming that the bottom happened is half a thesis, not all
   of it. A company exiting a capex J-curve trough earns "turnaround_hope", not "triumph".
4. ANNOUNCEMENTS != CAPEX: separate photo-op announcements from committed,
   funded, operational reality.
5. CASH IS THE TRUTH: OCF/EBITDA below ~0.7 means the P&L is writing cheques
   the cash flow statement isn't honouring.

Use web search to find: (a) the most recent comparable quarterly results of 2-4
named direct peers, (b) what the market/analysts expected for this company, and
(c) relevant sector context. Cite the actual numbers you find in key_evidence.

MOOD VOCABULARY (pick exactly one):
- triumph: genuine blowout, cash-backed, better than peers AND expectations
- steady: compounding as expected, no drama, quality intact
- grind: flattish, fighting through, neither winning nor losing
- turnaround_hope: inflection visible after a bad stretch — real but unproven
- distress: deteriorating fundamentals, real trouble
- illusion: LOOKS like a beat on headlines, but hollow underneath (cash, take-rate, one-offs)
- shock: sudden severe deterioration or a guidance bomb nobody saw coming

intensity (0-1) = how strongly the mood applies. grade = the quarter's report card.
music_brief = 3-4 sentences on how this should sound (tempo, weight, resolution).

End your response with EXACTLY ONE fenced json block matching this schema:
```json
""" + VERDICT_SCHEMA_HINT + """
```
No other fenced json blocks anywhere in your response."""


# ---------------------------------------------------------------------------
# Online judge — Fable 5 + web search
# ---------------------------------------------------------------------------

def judge_online(d, verbose=True):
    import anthropic
    from dotenv import load_dotenv
    load_dotenv()

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env/.env

    user_msg = (
        "Judge this quarterly result. Search for peer quarterlies and market "
        "expectations before concluding.\n\n```json\n"
        + json.dumps(d, indent=2) + "\n```"
    )
    messages = [{"role": "user", "content": user_msg}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]

    response = None
    for _ in range(5):  # pause_turn continuation cap
        response = client.messages.create(
            model="claude-fable-5",
            max_tokens=16000,
            thinking={"type": "adaptive"},
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

    text = "\n".join(b.text for b in response.content if b.type == "text")
    if verbose:
        # the judge's prose reasoning, minus the JSON tail
        prose = re.sub(r"```json.*?```", "", text, flags=re.S).strip()
        if prose:
            print("\n--- Judge's reasoning " + "-" * 40)
            print(prose[:2500])
            print("-" * 62)

    fences = re.findall(r"```json\s*(.*?)```", text, flags=re.S)
    if not fences:
        raise RuntimeError("Judge returned no JSON verdict. Raw tail:\n" + text[-800:])
    verdict = json.loads(fences[-1])
    return normalize(verdict)


# ---------------------------------------------------------------------------
# Offline judge — deterministic rules (no API)
# ---------------------------------------------------------------------------

def judge_offline(d):
    rev = d["revenue"]
    yoy = (rev[-1] / rev[-5] - 1) if len(rev) >= 5 else (rev[-1] / rev[0] - 1)
    margins = d["ebitda_margin"]
    margin_trend = margins[-1] - margins[0]
    leverage = d.get("net_debt_to_ebitda", 0.0)
    cash_conv = d.get("ocf_to_ebitda", 1.0)
    eps_surprise = d.get("eps_surprise_pct", 0.0)
    one_offs = d.get("one_off_items", False)

    red_flags = []
    if cash_conv < 0.7:
        red_flags.append(f"Cash conversion {cash_conv:.0%} — P&L not backed by cash")
    if one_offs:
        red_flags.append("One-off items inflating reported numbers")
    if leverage > 3.5:
        red_flags.append(f"Leverage {leverage:.1f}x EBITDA")
    if margin_trend < -0.02:
        red_flags.append(f"Margins compressed {margin_trend:+.1%} over the period")

    # mood rules, checked in priority order
    # a J-curve trough must have DEPTH: at least 2pp below both ends of the
    # window, else every seasonal zigzag reads as a turnaround
    trough = min(margins)
    trough_idx = margins.index(trough)
    recovering = (0 < trough_idx < len(margins) - 1
                  and margins[0] - trough >= 0.02
                  and margins[-1] - trough >= 0.02)

    # illusion: a "beat" that the cash doesn't back. Two routes in:
    #  (a) positive surprise on hollow cash/one-offs
    #  (b) spectacular headline growth with terrible cash conversion — the
    #      gross-revenue illusion needs no analyst estimates to be visible
    if (eps_surprise > 0 and (cash_conv < 0.6 or (one_offs and cash_conv < 0.8))) \
            or (yoy > 0.30 and cash_conv < 0.6):
        mood = "illusion"
    elif yoy < -0.15 or eps_surprise < -0.15:
        mood = "shock"
    elif recovering and yoy > 0:
        mood = "turnaround_hope"
    elif yoy > 0.15 and cash_conv >= 0.8:
        mood = "triumph"
    elif yoy > 0.02:
        mood = "steady"
    elif yoy > -0.05:
        mood = "grind"
    else:
        mood = "distress"

    intensity = float(min(1.0, 0.4 + abs(yoy) * 1.5 + abs(eps_surprise)))

    def clamp10(x):
        return int(max(0, min(10, round(x))))

    scores = {
        "growth_vs_past": clamp10(5 + yoy * 25),
        "vs_peers": 5,             # unknown offline — explicitly neutral
        "vs_expectations": clamp10(5 + eps_surprise * 40),
        "margin_quality": clamp10(margins[-1] * 25 + margin_trend * 60),
        "cash_quality": clamp10(cash_conv * 10 - (3 if one_offs else 0)),
        "balance_sheet": clamp10(10 - leverage * 1.8),
    }
    avg = sum(scores.values()) / len(scores)
    grades = [(8.5, "A+"), (7.5, "A"), (6.5, "B+"), (5.5, "B"), (4.5, "C+"), (3.5, "C"), (2.5, "D")]
    grade = next((g for cut, g in grades if avg >= cut), "F")

    return normalize({
        "mood": mood,
        "intensity": intensity,
        "grade": grade,
        "scores": scores,
        "headline": f"{d.get('company','Company')}: {mood.replace('_',' ')} quarter "
                    f"(YoY {yoy:+.1%}, cash conv {cash_conv:.0%}) [offline rules — peers not assessed]",
        "key_evidence": [
            f"Revenue YoY {yoy:+.1%}",
            f"EBITDA margin {margins[-1]:.1%} ({margin_trend:+.1%} over period)",
            f"OCF/EBITDA {cash_conv:.0%}",
            f"EPS surprise {eps_surprise:+.1%}",
        ],
        "red_flags": red_flags,
        "music_brief": f"Offline ruling: render as {mood}, intensity {intensity:.2f}.",
    })


# ---------------------------------------------------------------------------

def normalize(v):
    """Defend against schema drift from the LLM."""
    if v.get("mood") not in MOODS:
        v["mood"] = "grind"
    v["intensity"] = float(max(0.0, min(1.0, v.get("intensity", 0.5))))
    v.setdefault("grade", "C+")
    v.setdefault("scores", {})
    for k in ("growth_vs_past", "vs_peers", "vs_expectations",
              "margin_quality", "cash_quality", "balance_sheet"):
        v["scores"][k] = int(max(0, min(10, v["scores"].get(k, 5))))
    v.setdefault("headline", "")
    v.setdefault("key_evidence", [])
    v.setdefault("red_flags", [])
    v.setdefault("music_brief", "")
    return v


def judge(d, offline=False, verbose=True):
    if offline:
        return judge_offline(d)
    return judge_online(d, verbose=verbose)


if __name__ == "__main__":
    offline = "--offline" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("usage: judge.py <quarterly.json> [--offline]")
        sys.exit(1)
    with open(args[0]) as f:
        data = json.load(f)
    print(json.dumps(judge(data, offline=offline), indent=2))
