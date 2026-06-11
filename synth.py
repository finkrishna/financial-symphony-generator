#!/usr/bin/env python3
"""
synth.py — Renderer A: synthesize the quarter from scratch. (v2: with vibes)

Four movements, driven by the judge's verdict (mood + intensity) on top of
the raw metrics:
  I.   Topline   — melody follows the revenue trajectory
  II.  Margins   — harmony richness from margin level, progression from mood
  III. Leverage  — bass drone heaviness from net debt / EBITDA
  IV.  Verdict   — the cadence renders the judgment

v2 sound engine: stereo field, mood-gated rhythm section, ping-pong echo,
vibrato and soft saturation. Deterministic — same input, same WAV.

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

# mood -> (kick beats per bar of 4, hat eighth pattern, drum gain factor)
DRUM_MAP = {
    "triumph":         ((0, 2), (1, 1, 1, 1, 1, 1, 1, 1), 1.0),
    "steady":          ((0,),   (1, 0, 1, 0, 1, 0, 1, 0), 0.7),
    "grind":           ((0, 2), (1, 0, 0, 0, 1, 0, 0, 0), 0.9),
    "turnaround_hope": ((0,),   (0, 0, 1, 0, 0, 0, 1, 0), 0.6),
    "distress":        ((),     (0, 0, 0, 0, 0, 0, 0, 0), 0.4),
    "illusion":        ((0, 2), (1, 1, 0, 1, 1, 0, 1, 1), 0.9),  # too slick
    "shock":           ((0, 1, 2, 3), (1, 0, 1, 0, 1, 0, 1, 0), 1.0),
}


# --- synthesis primitives ----------------------------------------------------

def note_freq(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def tone(freq, dur, amp=0.5, harmonics=((1, 1.0), (2, 0.45), (3, 0.22), (4, 0.10), (5, 0.05)),
         attack=0.02, release=0.15, detune_cents=0.0, vibrato=0.004):
    if detune_cents:
        freq = freq * 2 ** (detune_cents / 1200.0)
    n = int(SR * dur)
    t = np.arange(n) / SR
    # gentle 5.5Hz vibrato, fading in — synthetic but alive
    vib = vibrato * np.minimum(t / 0.4, 1.0) * np.sin(2 * np.pi * 5.5 * t)
    sig = np.zeros(n)
    for mult, weight in harmonics:
        sig += weight * np.sin(2 * np.pi * freq * mult * (t + vib))
    sig /= sum(w for _, w in harmonics)
    sig = np.tanh(1.6 * sig) / np.tanh(1.6)  # soft saturation: warmth
    env = np.ones(n)
    a, r = max(1, int(SR * attack)), max(1, int(SR * release))
    if a + r >= n:
        a = r = n // 3
    env[:a] = np.linspace(0, 1, a)
    env[-r:] = np.linspace(1, 0, r)
    return (amp * sig * env).astype(np.float32)


def kick(amp=0.8):
    n = int(SR * 0.28)
    t = np.arange(n) / SR
    sweep = 110 * np.exp(-t * 14) + 42
    phase = 2 * np.pi * np.cumsum(sweep) / SR
    sig = np.sin(phase) * np.exp(-t * 16)
    click = np.exp(-t * 400) * 0.4
    return (amp * np.tanh(1.8 * (sig + click))).astype(np.float32)


def hat(rng, amp=0.22, dur=0.06):
    n = int(SR * dur)
    noise = rng.standard_normal(n)
    bright = np.diff(noise, prepend=0.0)  # crude highpass
    env = np.exp(-np.arange(n) / SR * 60)
    return (amp * 0.3 * bright * env).astype(np.float32)


def thud(amp=0.5):
    n = int(SR * 0.5)
    t = np.arange(n) / SR
    sig = np.sin(2 * np.pi * 55 * t) * np.exp(-t * 7)
    return (amp * sig).astype(np.float32)


def place(bufL, bufR, sound, start_sec, pan=0.0, gain=1.0):
    """pan in [-1, 1]; equal-power."""
    i = int(start_sec * SR)
    j = min(i + len(sound), len(bufL))
    if i >= len(bufL):
        return
    s = sound[: j - i]
    th = (pan + 1) * math.pi / 4
    bufL[i:j] += s * gain * math.cos(th)
    bufR[i:j] += s * gain * math.sin(th)


def pingpong_echo(bufL, bufR):
    """Feedforward multi-tap echo, alternating sides: cheap space, big vibe."""
    mono = (bufL + bufR) * 0.5
    for delay, g, left in ((0.131, 0.34, True), (0.197, 0.22, False),
                           (0.293, 0.14, True), (0.401, 0.08, False)):
        d = int(delay * SR)
        tap = np.zeros_like(mono)
        tap[d:] = mono[:-d] * g
        if left:
            bufL += tap
        else:
            bufR += tap


# --- parameters from metrics + verdict --------------------------------------

def params(d, verdict):
    mood = verdict["mood"]
    intensity = verdict["intensity"]
    scale, prog, base_bpm, bpm_span, cadence = MOOD_MAP[mood]

    rev = d["revenue"]
    margins = d["ebitda_margin"]
    leverage = d.get("net_debt_to_ebitda", 0.0)
    cash_conv = d.get("ocf_to_ebitda", 1.0)

    p = {"mood": mood, "intensity": intensity, "scale": scale,
         "progression": prog, "cadence": cadence}
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

def mv_topline(L, R, t0, p):
    beat, scale, root = p["beat"], p["scale"], p["root"] + 12
    t = t0
    for i, deg in enumerate(p["contour"]):
        octave, pos = divmod(deg, 7)
        midi = root + 12 + 12 * octave + scale[pos]
        dur = beat * (1.5 if i == len(p["contour"]) - 1 else 0.95)
        pan = 0.25 * math.sin(i * 1.1)  # melody wanders gently across the field
        place(L, R, tone(note_freq(midi), dur, amp=0.42, detune_cents=p["detune"]), t, pan)
        if i % 2 == 0:
            place(L, R, tone(note_freq(p["root"]), beat * 0.9, amp=0.20, vibrato=0), t)
        t += beat
    return t + beat * 0.5


def mv_margins(L, R, t0, p):
    beat, scale, root = p["beat"], p["scale"], p["root"]
    t = t0
    for degree in p["progression"]:
        notes = triad(scale, root + 12, degree, wide=p["chord_wide"])
        if p["chord_gap"]:
            notes = [notes[0], notes[2]]
        spread = np.linspace(-0.5, 0.5, len(notes))  # chord opens across stereo
        for midi, pan in zip(notes, spread):
            place(L, R, tone(note_freq(midi), beat * 3.6, amp=0.30 / max(1, len(notes) - 1),
                             attack=0.08, release=0.5), t, float(pan))
        t += beat * 4
    return t


def mv_leverage(L, R, t0, p):
    beat, root = p["beat"], p["root"] - 12
    t = t0
    dur = beat * 8
    place(L, R, tone(note_freq(root), dur, amp=0.5 * p["bass_gain"],
                     harmonics=((1, 1.0), (2, 0.5), (0.5, 0.3)), attack=0.3, release=1.0,
                     vibrato=0), t)
    place(L, R, tone(note_freq(root + 7), dur, amp=0.25 * p["bass_gain"],
                     attack=0.5, release=1.0, vibrato=0), t)
    if p["bass_dark"]:
        place(L, R, tone(note_freq(root + 6), dur * 0.6, amp=0.30 * p["bass_gain"],
                         attack=0.8, release=1.2, vibrato=0), t + dur * 0.3, pan=-0.3)
    if p["one_offs"]:
        place(L, R, tone(note_freq(p["root"] + 13), beat * 0.5, amp=0.5,
                         attack=0.005, release=0.1), t + dur * 0.5, pan=0.6)
    return t + dur


def triad(scale, root_midi, degree, wide=False):
    notes = []
    for step in (0, 2, 4):
        idx = degree + step
        octave, pos = divmod(idx, 7)
        notes.append(root_midi + 12 * octave + scale[pos])
    if wide:
        notes.append(notes[0] + 12)
    return notes


def mv_verdict(L, R, t0, p):
    beat, scale, root = p["beat"], p["scale"], p["root"] + 12
    t = t0

    def chord(degree, dur, use_scale=None, use_root=None, amp=0.36):
        sc = use_scale or scale
        rt = use_root if use_root is not None else root
        notes = triad(sc, rt, degree, wide=True)
        spread = np.linspace(-0.6, 0.6, len(notes))
        for midi, pan in zip(notes, spread):
            place(L, R, tone(note_freq(midi), dur, amp=amp / 3, attack=0.05, release=0.6),
                  t, float(pan))
        place(L, R, tone(note_freq(rt - 24 + sc[degree % 7]), dur,
                         amp=0.3 * p["bass_gain"], attack=0.1, release=0.8, vibrato=0), t)

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


def rhythm(L, R, t0, t1, p):
    """Mood-gated drums from t0 to t1, fading out over the last two bars."""
    mood, beat = p["mood"], p["beat"]
    kicks, hat_pat, factor = DRUM_MAP[mood]
    gain = (0.30 + 0.45 * p["intensity"]) * factor
    rng = np.random.default_rng(42)  # deterministic — of course it's 42
    fade_start = t1 - 8 * beat
    k, h, th = kick(), hat(rng), thud()
    bar = 0
    t = t0
    while t < t1:
        g = gain * (1.0 if t < fade_start else max(0.0, (t1 - t) / (8 * beat)))
        if mood == "distress":
            if bar % 2 == 0:
                place(L, R, th, t, gain=g)
        else:
            for kb in kicks:
                place(L, R, k, t + kb * beat, gain=g)
            # hope builds: hats only join in the second half
            if mood != "turnaround_hope" or t > t0 + (t1 - t0) * 0.45:
                for i, on in enumerate(hat_pat):
                    if on:
                        place(L, R, hat(rng), t + i * beat / 2,
                              pan=0.35 if i % 2 else -0.35, gain=g)
        t += 4 * beat
        bar += 1


# --- driver ------------------------------------------------------------------

def render(d, verdict, out_path):
    p = params(d, verdict)
    n = int(SR * 120)
    L = np.zeros(n, dtype=np.float32)
    R = np.zeros(n, dtype=np.float32)
    t = 0.5
    t = mv_topline(L, R, t, p)
    t = mv_margins(L, R, t, p)
    t = mv_leverage(L, R, t, p)
    t_end = mv_verdict(L, R, t, p)
    rhythm(L, R, 0.5, t, p)  # drums run under movements I-III, stop for the verdict
    L, R = L[: int(SR * (t_end + 1.5))], R[: int(SR * (t_end + 1.5))]
    pingpong_echo(L, R)
    peak = max(np.abs(L).max(), np.abs(R).max())
    if peak > 0:
        L, R = L * (0.85 / peak), R * (0.85 / peak)
    pcm = np.empty(2 * len(L), dtype=np.int16)
    pcm[0::2] = (L * 32767).astype(np.int16)
    pcm[1::2] = (R * 32767).astype(np.int16)
    with wave.open(out_path, "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return {
        "path": out_path, "seconds": len(L) / SR, "bpm": round(p["bpm"]),
        "key": "major" if p["scale"] == MAJOR else "minor",
        "cadence": p["cadence"], "detune": p["detune"], "bass_gain": round(p["bass_gain"], 2),
    }
