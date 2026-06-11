#!/usr/bin/env python3
"""
Financial Symphony Generator
Turns a quarterly financial result into a four-movement musical piece.

The mappings are opinionated and follow real research discipline:
  I.   Topline   — melody follows the revenue trajectory; growth sets key & tempo
  II.  Margins   — harmony richness from margin level, progression from trend
  III. Leverage  — bass drone heaviness from net debt / EBITDA
  IV.  Verdict   — the cadence: cash-backed beats resolve, accounting beats deceive

Signature rule (the "gross-revenue illusion"): if cash conversion is poor,
the melody is slightly detuned against the harmony — almost right, but off.

Usage:
    python3 symphony.py examples/steady_compounder.json
    python3 symphony.py examples/jcurve_utility.json -o gipcl.wav
"""

import argparse
import json
import math
import os
import struct
import sys
import wave

import numpy as np

SR = 44100  # sample rate


# ---------------------------------------------------------------------------
# Synthesis primitives
# ---------------------------------------------------------------------------

def note_freq(midi):
    """MIDI note number -> frequency in Hz."""
    return 440.0 * 2 ** ((midi - 69) / 12)


def tone(freq, dur, amp=0.5, harmonics=((1, 1.0), (2, 0.35), (3, 0.15), (4, 0.08)),
         attack=0.02, release=0.15, detune_cents=0.0):
    """Additive-synthesis note with ADSR-ish envelope. Returns float32 array."""
    if detune_cents:
        freq = freq * 2 ** (detune_cents / 1200.0)
    n = int(SR * dur)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for mult, weight in harmonics:
        sig += weight * np.sin(2 * np.pi * freq * mult * t)
    sig /= sum(w for _, w in harmonics)

    env = np.ones(n)
    a = max(1, int(SR * attack))
    r = max(1, int(SR * release))
    if a + r >= n:  # very short note
        a = n // 3
        r = n // 3
    env[:a] = np.linspace(0, 1, a)
    env[-r:] = np.linspace(1, 0, r)
    return (amp * sig * env).astype(np.float32)


def place(buf, sound, start_sec, gain=1.0):
    """Mix `sound` into `buf` at start_sec (both float32)."""
    i = int(start_sec * SR)
    j = min(i + len(sound), len(buf))
    if i < len(buf):
        buf[i:j] += sound[: j - i] * gain


# ---------------------------------------------------------------------------
# Music theory helpers
# ---------------------------------------------------------------------------

MAJOR = [0, 2, 4, 5, 7, 9, 11]
NAT_MINOR = [0, 2, 3, 5, 7, 8, 10]
HARM_MINOR = [0, 2, 3, 5, 7, 8, 11]

# Chord progressions by mood (scale degrees, 0-indexed)
PROG_TRIUMPH = [0, 3, 4, 0]        # I  IV V  I
PROG_RISING = [0, 5, 3, 4]         # I  vi IV V   (keeps lifting)
PROG_GRIND = [0, 3, 0, 4]          # I  IV I  V   (workmanlike)
PROG_DESCENT = [0, 6, 5, 4]        # i  VII VI V  (the lament bass)
PROG_DISTRESS = [0, 1, 4, 0]       # i  ii° V  i


def triad(scale, root_midi, degree, wide=False):
    """Build a triad (or wider voicing) on a scale degree. Returns midi notes."""
    notes = []
    for step in (0, 2, 4):
        idx = degree + step
        octave, pos = divmod(idx, 7)
        notes.append(root_midi + 12 * octave + scale[pos])
    if wide:
        notes.append(notes[0] + 12)  # double the root an octave up
    return notes


# ---------------------------------------------------------------------------
# Financial interpretation
# ---------------------------------------------------------------------------

def interpret(d):
    """Derive all musical parameters from the quarterly metrics."""
    rev = d["revenue"]  # list of recent quarters, oldest first
    yoy = (rev[-1] / rev[-5] - 1) if len(rev) >= 5 else (rev[-1] / rev[0] - 1)
    qoq = rev[-1] / rev[-2] - 1 if len(rev) >= 2 else 0.0

    margins = d["ebitda_margin"]  # same quarters, fractions
    margin_now = margins[-1]
    margin_trend = margins[-1] - margins[0]

    leverage = d.get("net_debt_to_ebitda", 0.0)
    cash_conv = d.get("ocf_to_ebitda", 1.0)
    eps_surprise = d.get("eps_surprise_pct", 0.0)
    one_offs = d.get("one_off_items", False)

    p = {}

    # --- Key & mode: the overall weather ---
    if yoy > 0.15:
        p["scale"], p["mood"] = MAJOR, "triumph"
    elif yoy > 0.02:
        p["scale"], p["mood"] = MAJOR, "steady"
    elif yoy > -0.05:
        p["scale"], p["mood"] = NAT_MINOR, "grind"
    else:
        p["scale"], p["mood"] = HARM_MINOR, "distress"

    # Root note: bigger companies sound deeper. Map log(revenue) to C2..C4 region.
    p["root"] = int(np.clip(60 - 4 * math.log10(max(rev[-1], 1)), 36, 55))

    # --- Tempo from growth: 66 (dirge) .. 152 (sprint) ---
    p["bpm"] = float(np.clip(100 + 220 * yoy, 66, 152))
    p["beat"] = 60.0 / p["bpm"]

    # --- Melody contour: normalize revenue path to scale degrees ---
    r = np.array(rev, dtype=float)
    span = r.max() - r.min()
    norm = (r - r.min()) / span if span > 0 else np.zeros(len(r))
    p["contour"] = [int(round(x * 7)) for x in norm]  # 0..7 scale degrees

    # --- Harmony from margins ---
    p["chord_wide"] = margin_now > 0.20          # fat margins: rich voicing
    p["chord_gap"] = margin_now < 0.08           # thin margins: hollow fifths
    if p["mood"] in ("triumph", "steady"):
        p["progression"] = PROG_RISING if margin_trend > 0.01 else PROG_GRIND
        if p["mood"] == "triumph":
            p["progression"] = PROG_TRIUMPH
    else:
        p["progression"] = PROG_DESCENT if margin_trend < -0.01 else PROG_DISTRESS

    # --- Bass from leverage ---
    p["bass_gain"] = float(np.clip(0.25 + 0.22 * leverage, 0.25, 1.2))
    p["bass_dark"] = leverage > 3.0              # add a tritone rumble when overlevered

    # --- The gross-revenue illusion: poor cash conversion detunes the melody ---
    if cash_conv >= 0.85:
        p["detune"] = 0.0
    elif cash_conv >= 0.6:
        p["detune"] = 18.0   # uneasy
    else:
        p["detune"] = 35.0   # clearly wrong to any attentive ear

    # --- The verdict cadence ---
    beat = eps_surprise > 0
    cash_backed = cash_conv >= 0.8
    if beat and cash_backed:
        p["cadence"] = "authentic"      # V -> I, fully resolved
    elif beat and not cash_backed:
        p["cadence"] = "deceptive"      # V -> vi: the beat that isn't
    elif not beat and cash_backed:
        p["cadence"] = "plagal"         # IV -> i: a dignified miss
    else:
        p["cadence"] = "unresolved"     # ends on V: nothing is settled

    p["one_offs"] = one_offs
    p["stats"] = dict(yoy=yoy, qoq=qoq, margin=margin_now, margin_trend=margin_trend,
                      leverage=leverage, cash_conv=cash_conv, eps_surprise=eps_surprise)
    return p


# ---------------------------------------------------------------------------
# The four movements
# ---------------------------------------------------------------------------

def mv_topline(buf, t0, p):
    """Movement I — the revenue line sings."""
    beat = p["beat"]
    scale, root = p["scale"], p["root"] + 12  # melody an octave above root
    t = t0
    for i, deg in enumerate(p["contour"]):
        octave, pos = divmod(deg, 7)
        midi = root + 12 + 12 * octave + scale[pos]
        dur = beat * (1.5 if i == len(p["contour"]) - 1 else 0.95)
        place(buf, tone(note_freq(midi), dur, amp=0.42,
                        detune_cents=p["detune"]), t)
        # light root-note pulse underneath
        if i % 2 == 0:
            place(buf, tone(note_freq(p["root"]), beat * 0.9, amp=0.20), t)
        t += beat
    return t + beat * 0.5


def mv_margins(buf, t0, p):
    """Movement II — harmony tells you about profitability."""
    beat = p["beat"]
    scale, root = p["scale"], p["root"]
    t = t0
    for degree in p["progression"]:
        notes = triad(scale, root + 12, degree, wide=p["chord_wide"])
        if p["chord_gap"]:
            notes = [notes[0], notes[2]]  # hollow fifth — no warmth in the middle
        for midi in notes:
            place(buf, tone(note_freq(midi), beat * 3.6, amp=0.30 / max(1, len(notes) - 1),
                            attack=0.08, release=0.5), t)
        t += beat * 4
    return t


def mv_leverage(buf, t0, p):
    """Movement III — the balance sheet speaks from below."""
    beat = p["beat"]
    root = p["root"] - 12
    t = t0
    dur = beat * 8
    place(buf, tone(note_freq(root), dur, amp=0.5 * p["bass_gain"],
                    harmonics=((1, 1.0), (2, 0.5), (0.5, 0.3)),
                    attack=0.3, release=1.0), t)
    place(buf, tone(note_freq(root + 7), dur, amp=0.25 * p["bass_gain"],
                    attack=0.5, release=1.0), t)
    if p["bass_dark"]:
        # over-leveraged: the tritone growls underneath
        place(buf, tone(note_freq(root + 6), dur * 0.6, amp=0.30 * p["bass_gain"],
                        attack=0.8, release=1.2), t + dur * 0.3)
    if p["one_offs"]:
        # a one-off item: brief dissonant stab that doesn't belong
        stab = tone(note_freq(p["root"] + 13), beat * 0.5, amp=0.5, attack=0.005, release=0.1)
        place(buf, stab, t + dur * 0.5)
    return t + dur


def mv_verdict(buf, t0, p):
    """Movement IV — the cadence renders judgment."""
    beat = p["beat"]
    scale, root = p["scale"], p["root"] + 12
    t = t0

    def chord(degree, dur, amp=0.36, wide=True):
        for midi in triad(scale, root, degree, wide=wide):
            place(buf, tone(note_freq(midi), dur, amp=amp / 3,
                            attack=0.05, release=0.6), t)
        place(buf, tone(note_freq(root - 24 + scale[degree % 7]), dur,
                        amp=0.3 * p["bass_gain"], attack=0.1, release=0.8), t)

    if p["cadence"] == "authentic":
        chord(4, beat * 2); t += beat * 2
        chord(0, beat * 6)                      # home, held long: all is well
    elif p["cadence"] == "deceptive":
        chord(4, beat * 2); t += beat * 2
        chord(5, beat * 6)                      # vi where I belonged: read the cash flow
    elif p["cadence"] == "plagal":
        chord(3, beat * 2); t += beat * 2
        chord(0, beat * 6)                      # honest amen for an honest miss
    else:  # unresolved
        chord(1, beat * 2); t += beat * 2
        chord(4, beat * 5)                      # ends on the dominant. see you next quarter.
    return t + beat * 6


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def generate(d):
    p = interpret(d)
    total = 75 + 30  # generous buffer; trimmed at the end
    buf = np.zeros(int(SR * total), dtype=np.float32)

    t = 0.5
    t = mv_topline(buf, t, p)
    t = mv_margins(buf, t, p)
    t = mv_leverage(buf, t, p)
    t = mv_verdict(buf, t, p)

    # trim and normalise
    end = int(SR * (t + 1.0))
    buf = buf[:end]
    peak = np.abs(buf).max()
    if peak > 0:
        buf = buf * (0.85 / peak)
    return buf, p


def write_wav(path, buf):
    pcm = (buf * 32767).astype(np.int16)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def describe(d, p):
    s = p["stats"]
    lines = [
        f"  {d.get('company', 'Company')} — {d.get('quarter', '')}",
        f"  Mood: {p['mood']}  |  Key: {'major' if p['scale'] == MAJOR else 'minor'}"
        f"  |  Tempo: {p['bpm']:.0f} bpm",
        f"  Revenue YoY {s['yoy']:+.1%}  ->  melody {'rises' if p['contour'][-1] >= p['contour'][0] else 'falls'}",
        f"  EBITDA margin {s['margin']:.1%} ({s['margin_trend']:+.1%} over period)"
        f"  ->  {'rich chords' if p['chord_wide'] else 'hollow fifths' if p['chord_gap'] else 'plain triads'}",
        f"  Net debt/EBITDA {s['leverage']:.1f}x  ->  bass weight {p['bass_gain']:.2f}"
        + ("  + tritone growl" if p["bass_dark"] else ""),
        f"  Cash conversion {s['cash_conv']:.0%}  ->  "
        + ("in tune" if p["detune"] == 0 else f"melody detuned {p['detune']:.0f} cents (something is off)"),
        f"  EPS surprise {s['eps_surprise']:+.1%}  ->  {p['cadence']} cadence",
    ]
    if p["one_offs"]:
        lines.append("  One-off items  ->  dissonant stab in movement III")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Turn a quarterly result into music.")
    ap.add_argument("input", help="JSON file with quarterly metrics")
    ap.add_argument("-o", "--output", help="Output WAV path (default: <company>_<quarter>.wav)")
    args = ap.parse_args()

    with open(args.input) as f:
        d = json.load(f)

    buf, p = generate(d)

    out = args.output
    if not out:
        base = f"{d.get('company', 'company')}_{d.get('quarter', 'q')}".replace(" ", "_").lower()
        out = base + ".wav"
    write_wav(out, buf)

    print("\n🎼 Financial Symphony")
    print(describe(d, p))
    print(f"\n  -> {out}  ({len(buf) / SR:.0f}s)")
    print(f"     play: afplay {out}\n")


if __name__ == "__main__":
    main()
