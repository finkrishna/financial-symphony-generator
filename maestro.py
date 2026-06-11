#!/usr/bin/env python3
"""
maestro.py — Financial Symphony Generator: the conductor.

    python3 maestro.py examples/jcurve_utility.json              # judge + both renderers
    python3 maestro.py result.json --song                        # judge + song only
    python3 maestro.py result.json --synth --offline             # rules-based, no API
    python3 maestro.py result.json --verdict-only                # judgment, no music
    python3 maestro.py result.json --lang hi                     # prefer Hindi anthem
    python3 maestro.py result.json --no-open --no-play           # quiet mode

Pipeline:  quarterly.json -> judge (Fable 5 + web search, or offline rules)
           -> verdict -> synth (.wav) and/or songbank anthem (YouTube).
"""

import argparse
import json
import subprocess

import judge as judge_mod
import songpick
import synth


def verdict_card(v):
    bar = "─" * 62
    lines = [bar, f"  GRADE {v['grade']}   |   mood: {v['mood']}   |   intensity {v['intensity']:.2f}", bar]
    lines.append(f"  {v['headline']}")
    s = v["scores"]
    lines.append("")
    lines.append(f"  growth vs past  {'█' * s['growth_vs_past']:<10} {s['growth_vs_past']}/10"
                 f"    vs peers        {'█' * s['vs_peers']:<10} {s['vs_peers']}/10")
    lines.append(f"  vs expectations {'█' * s['vs_expectations']:<10} {s['vs_expectations']}/10"
                 f"    margin quality  {'█' * s['margin_quality']:<10} {s['margin_quality']}/10")
    lines.append(f"  cash quality    {'█' * s['cash_quality']:<10} {s['cash_quality']}/10"
                 f"    balance sheet   {'█' * s['balance_sheet']:<10} {s['balance_sheet']}/10")
    if v["key_evidence"]:
        lines.append("\n  Evidence:")
        lines += [f"   • {e}" for e in v["key_evidence"][:6]]
    if v["red_flags"]:
        lines.append("\n  ⚠ Red flags:")
        lines += [f"   • {r}" for r in v["red_flags"]]
    if v.get("music_brief"):
        lines.append(f"\n  Music brief: {v['music_brief']}")
    lines.append(bar)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Quarterly result -> judgment -> music.")
    ap.add_argument("input", help="quarterly result JSON")
    ap.add_argument("--synth", action="store_true", help="render synthesized symphony only")
    ap.add_argument("--song", action="store_true", help="pick songbank anthem only")
    ap.add_argument("--verdict-only", action="store_true", help="judge, no music")
    ap.add_argument("--offline", action="store_true", help="rules-based judge, no API")
    ap.add_argument("--lang", choices=["hi", "en"], help="prefer Hindi or English anthem")
    ap.add_argument("--no-open", action="store_true", help="print song link, don't open browser")
    ap.add_argument("--no-play", action="store_true", help="don't afplay the rendered wav")
    ap.add_argument("-o", "--output", help="wav output path")
    args = ap.parse_args()

    with open(args.input) as f:
        d = json.load(f)

    company = d.get("company", "company")
    quarter = d.get("quarter", "q")
    slug = f"{company}_{quarter}".replace(" ", "_").lower()

    print(f"\n🎼 {company} — {quarter}")
    print("  Judging" + (" (offline rules)..." if args.offline else " (Fable 5 + web search — this takes a minute)..."))

    v = judge_mod.judge(d, offline=args.offline)
    print("\n" + verdict_card(v))

    vpath = f"verdict_{slug}.json"
    with open(vpath, "w") as f:
        json.dump(v, f, indent=2)
    print(f"  verdict saved -> {vpath}")

    if args.verdict_only:
        return

    do_synth = args.synth or not args.song
    do_song = args.song or not args.synth

    if do_synth:
        out = args.output or f"{slug}.wav"
        info = synth.render(d, v, out)
        print(f"\n🎻 Synthesized: {out}  ({info['seconds']:.0f}s, {info['bpm']} bpm, "
              f"{info['key']}, {info['cadence']} cadence"
              + (f", detuned {info['detune']:.0f}c" if info["detune"] else "") + ")")
        if not args.no_play:
            print("   playing...")
            subprocess.run(["afplay", out], check=False)
        else:
            print(f"   play: afplay {out}")

    if do_song:
        winner, runners = songpick.pick(v, company, quarter, lang=args.lang)
        print(songpick.announce(winner, v, runners))
        if not args.no_open:
            songpick.play(winner)


if __name__ == "__main__":
    main()
