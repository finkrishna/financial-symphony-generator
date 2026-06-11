#!/usr/bin/env python3
"""
synth.py — Renderer A: synthesize the quarter from scratch.

Four movements, driven by the judge's verdict (mood + intensity) on top of
the raw metrics:
  I.   Topline   — melody follows the revenue trajectory
  II.  Margins   — harmony richness from margin level, progression from mood
  III. Leverage  — bass drone heaviness from net debt / EBITDA
  IV.  Verdict   — the cadence renders the judgment

Mood rules:
  - "illusion" forces the detuned melody + deceptive cadence (judge outranks metrics)
  - "turnaround_hope" gets the dawn cadence: minor home resolving into the
    relative major — the J-curve in sound
"""

import math
import wave

import numpy as np

SR = 44100

MAJOR = [0, 2, 4, 5, 7, 9, 11]
NAT_MINOR = [0, 2, 3, 5, 7, 8, 10]
HARM_MINOR = [0, 2, 3, 5, 7, 8, 11]

PROG_TRIUMPH = [0, 3, 4, 0]
PROG_RISING = [0, 5, 3, 4]
PROG_GRIND = [0, 3, 0, 4]
PROG_DESCENT = [0, 6, 5, 4]
PROG_DISTRESS = [0, 1, 4, 0]

# mood -> (scale, progression, base_bpm, bpm_span, cadence)
MOOD_MAP = {
    "triumph":         (MAJOR,      PROG_TRIUMPH,  116, 36, "authentic"),
    "steady":          (MAJOR,      PROG_RISING,   100, 20, "authentic"),
    "grind":           (NAT_MINOR,  PROG_GRIND,     88, 16, "plagal"),
    "turnaround_hope": (HARM_MINOR, PROG_RISING,    92, 24, "dawn"),
    "distress":        (HARM_MINOR, PROG_DISTRESS,  68, 12, "unresolved"),
    "illusion":        (MAJOR,      PROG_RISING,   124, 28, "deceptive"),
    "shock":           (NAT_MINOR,  PROG_DESCENT,  132, 20, "unresolved"),
}


# --- synthesis primitives (proven in v1) -----------------------------------

def note_freq(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def tone(freq, dur, amp=0.5, harmonics=((1, 1.0), (2, 0.35), (3, 0.15), (4, 0.08)),
         attack=0.02, release=0.15, detune_cents=0.0):
    if detune_cents:
        freq = freq * 2 ** (detune_cents / 1200.0)
    n = int(SR * dur)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for mult, weight in harmonics:
        sig += weight * np.sin(2 * np.pi * freq * mult * t)
    sig /= sum(w for _, w in harmonics)
    env = np.ones(n)
    a, r = max(1, int(SR * attack)), max(1, int(SR * release))
    if a + r >= n:
        a = r = n // 3
    env[:a] = np.linspace(0, 1, a)
    env[-r:] = np.linspace(1, 0, r)
    return (amp * sig * env).astype(np.float32)


def place(buf, sound, start_sec, gain=1.0):
    i = int(start_sec * SR)
    j = min(i + len(sound), len(buf))
    if i < len(buf):
        buf[i:j] += sound[: j - i] * gain


def triad(scale, root_midi, degree, wide=False):
    notes = []
    for step in (0, 2, 4):
        idx = degree + step
        octave, pos = divmod(idx, 7)
        notes.append(root_midi + 12 * octave + scale[pos])
    if wide:
        notes.append(notes[0] + 12)
    return notes


# --- parameters from metrics + verdict --------------------------------------

def params(d, verdict):
    mood = verdict["mood"]
    intensity = verdict["intensity"]
    scale, prog, base_bpm, bpm_span, cadence = MOOD_MAP[mood]

    rev = d["revenue"]
    margins = d["ebitda_margin"]
    leverage = d.get("net_debt_to_ebitda", 0.0)
    cash_conv = d.get("ocf_to_ebitda", 1.0)

    p = {"mood": mood, "scale": scale, "progression": prog, "cadence": cadence}
    p["bpm"] = base_bpm + bpm_span * intensity
    p["beat"] = 60.0 / p["bpm"]
    p["root"] = int(np.clip(60 - 4 * math.log10(max(rev[-1], 1)), 36, 55))

    r = np.array(rev, dtype=float)
    span = r.max() - r.min()
    norm = (r - r.min()) / span if span > 0 else np.zeros(len(r))
    p["contour"] = [int(round(x * 7)) for x in norm]

    p["chord_wide"] = margins[-1] > 0.20
    p["chord_gap"] = margins[-1] < 0.08

    p["bass_gain"] = float(np.clip(0.25 + 0.22 * leverage, 0.25, 1.2))
    p["bass_dark"] = leverage > 3.0

    if mood == "illusion":
        p["detune"] = 35.0  # the judge has ruled: it sounds right but isn't
    elif cash_conv >= 0.85:
        p["detune"] = 0.0
    elif cash_conv >= 0.6:
        p["detune"] = 18.0
    else:
        p["detune"] = 35.0

    p["one_offs"] = d.get("one_off_items", False) or mood == "shock"
    return p


# --- the four movements ------------------------------------------------------

def mv_topline(buf, t0, p):
    beat, scale, root = p["beat"], p["scale"], p["root"] + 12
    t = t0
    for i, deg in enumerate(p["contour"]):
        octave, pos = divmod(deg, 7)
        midi = root + 12 + 12 * octave + scale[pos]
        dur = beat * (1.5 if i == len(p["contour"]) - 1 else 0.95)
        place(buf, tone(note_freq(midi), dur, amp=0.42, detune_cents=p["detune"]), t)
        if i % 2 == 0:
            place(buf, tone(note_freq(p["root"]), beat * 0.9, amp=0.20), t)
        t += beat
    return t + beat * 0.5


def mv_margins(buf, t0, p):
    beat, scale, root = p["beat"], p["scale"], p["root"]
    t = t0
    for degree in p["progression"]:
        notes = triad(scale, root + 12, degree, wide=p["chord_wide"])
        if p["chord_gap"]:
            notes = [notes[0], notes[2]]
        for midi in notes:
            place(buf, tone(note_freq(midi), beat * 3.6, amp=0.30 / max(1, len(notes) - 1),
                            attack=0.08, release=0.5), t)
        t += beat * 4
    return t


def mv_leverage(buf, t0, p):
    beat, root = p["beat"], p["root"] - 12
    t = t0
    dur = beat * 8
    place(buf, tone(note_freq(root), dur, amp=0.5 * p["bass_gain"],
                    harmonics=((1, 1.0), (2, 0.5), (0.5, 0.3)), attack=0.3, release=1.0), t)
    place(buf, tone(note_freq(root + 7), dur, amp=0.25 * p["bass_gain"],
                    attack=0.5, release=1.0), t)
    if p["bass_dark"]:
        place(buf, tone(note_freq(root + 6), dur * 0.6, amp=0.30 * p["bass_gain"],
                        attack=0.8, release=1.2), t + dur * 0.3)
    if p["one_offs"]:
        place(buf, tone(note_freq(p["root"] + 13), beat * 0.5, amp=0.5,
                        attack=0.005, release=0.1), t + dur * 0.5)
    return t + dur


def mv_verdict(buf, t0, p):
    beat, scale, root = p["beat"], p["scale"], p["root"] + 12
    t = t0

    def chord(degree, dur, use_scale=None, use_root=None, amp=0.36):
        sc = use_scale or scale
        rt = use_root if use_root is not None else root
        for midi in triad(sc, rt, degree, wide=True):
            place(buf, tone(note_freq(midi), dur, amp=amp / 3, attack=0.05, release=0.6), t)
        place(buf, tone(note_freq(rt - 24 + sc[degree % 7]), dur,
                        amp=0.3 * p["bass_gain"], attack=0.1, release=0.8), t)

    c = p["cadence"]
    if c == "authentic":
        chord(4, beat * 2); t += beat * 2
        chord(0, beat * 6)
    elif c == "deceptive":
        chord(4, beat * 2); t += beat * 2
        chord(5, beat * 6)
    elif c == "plagal":
        chord(3, beat * 2); t += beat * 2
        chord(0, beat * 6)
    elif c == "dawn":
        # minor home... then the relative major opens like first light
        chord(0, beat * 2); t += beat * 2
        chord(4, beat * 2); t += beat * 2
        chord(0, beat * 5, use_scale=MAJOR, use_root=root + 3)  # relative major
    else:  # unresolved
        chord(1, beat * 2); t += beat * 2
        chord(4, beat * 5)
    return t + beat * 6


# --- driver ------------------------------------------------------------------

def render(d, verdict, out_path):
    p = params(d, verdict)
    buf = np.zeros(int(SR * 120), dtype=np.float32)
    t = 0.5
    t = mv_topline(buf, t, p)
    t = mv_margins(buf, t, p)
    t = mv_leverage(buf, t, p)
    t = mv_verdict(buf, t, p)
    buf = buf[: int(SR * (t + 1.0))]
    peak = np.abs(buf).max()
    if peak > 0:
        buf = buf * (0.85 / peak)
    pcm = (buf * 32767).astype(np.int16)
    with wave.open(out_path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return {
        "path": out_path, "seconds": len(buf) / SR, "bpm": round(p["bpm"]),
        "key": "major" if p["scale"] == MAJOR else "minor",
        "cadence": p["cadence"], "detune": p["detune"], "bass_gain": round(p["bass_gain"], 2),
    }
