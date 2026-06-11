# Financial Symphony Generator 🎼

Feed it a quarterly result. It judges the quarter like a disciplined analyst —
against the company's own past, against competition, against market
expectations — then renders the verdict as **music**.

Two renderers:

1. **Synthesizer** — composes a four-movement piece from scratch
2. **Songbank** — matches the verdict's mood to a curated Hindi/English song
   and opens it on YouTube. *"This quarter's anthem."*

```
quarterly.json ──► judge (Claude Fable 5 + web search) ──► verdict ──┬──► symphony.wav
                                                                     └──► YouTube anthem
```

*A tribute to Douglas Adams. There's a song for this. DON'T PANIC.*

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # add your Anthropic API key

python3 maestro.py examples/jcurve_utility.json              # judge + both renderers
python3 maestro.py result.json --song --lang hi              # Hindi anthem only
python3 maestro.py result.json --synth --offline             # no API: rules-based judge
python3 maestro.py result.json --verdict-only                # just the judgment
```

The online judge costs roughly ₹5–15 per run (web searches + reasoning).
`--offline` is free and instant but can't see peers or expectations.

## Input format

```json
{
  "company": "JCurve Utility",
  "quarter": "Q4 FY26",
  "revenue": [820, 800, 790, 805, 795, 810, 850, 905],
  "ebitda_margin": [0.31, 0.29, 0.26, 0.24, 0.22, 0.21, 0.22, 0.24],
  "net_debt_to_ebitda": 4.2,
  "ocf_to_ebitda": 0.88,
  "eps_surprise_pct": -0.06,
  "one_off_items": false
}
```

`revenue` and `ebitda_margin`: recent quarters, oldest first (8 is ideal).
Use a real listed company's numbers and the online judge will find its actual
peers and street expectations by itself.

## The mood vocabulary

The judge must pick exactly one — this drives everything downstream:

| Mood | Means | Synth signature | Anthem examples |
|---|---|---|---|
| `triumph` | Cash-backed blowout, beats peers AND expectations | Major, fast, authentic cadence | Chak De! India, Eye of the Tiger |
| `steady` | Compounding on plan, no drama | Major, moderate, resolves home | Aashayein, Lovely Day |
| `grind` | Flattish, fighting through | Minor, workmanlike | Kar Har Maidaan Fateh, The Boxer |
| `turnaround_hope` | Inflection visible, unproven | Minor opening → **relative-major dawn** | Roobaroo, I Can See Clearly Now |
| `distress` | Real deterioration | Harmonic minor, slow, unresolved | Waqt Ne Kiya..., Hurt |
| `illusion` | Headline beat, hollow inside | Major but **detuned 35¢**, deceptive cadence | Jhooth Bole Kauwa Kaate, The Great Pretender |
| `shock` | Guidance bomb / sudden collapse | Fast minor descent, dissonant stab | Yeh Kya Hua, Mad World |

## The research discipline (baked into the judge)

- **Gross-revenue illusion**: decompose to net take-rate before judging fintech growth
- **One-off mirage**: one-time items never earn a grade upgrade
- **Trough ≠ thesis**: exiting a capex J-curve earns `turnaround_hope`, not `triumph`
- **Cash is the truth**: OCF/EBITDA < 0.7 and the P&L is writing cheques the cash flow won't honour

The synthesizer encodes the same discipline: poor cash conversion literally
**detunes the melody** — it sounds almost right, like the accounts.

## The songbank

`songbank.json` — ~40 songs, mood-tagged, energy-rated, each with a
`why_it_fits`. The matcher picks by mood + energy-vs-intensity proximity, with
a deterministic tiebreak so the same quarter always gets the same anthem.
**Curating this file is the fun part.** Add songs; PRs to taste.

## Web app

```bash
python3 app.py                # http://localhost:5050
```

Paste a quarterly JSON (or click an archetype), get the verdict card, the
anthem with a YouTube link, and the synthesized WAV in an audio player.
The public path uses the free offline judge; the paid Fable 5 judge answers
only to `ONLINE_TOKEN`. Deploys to Render via `render.yaml` (free tier) —
set `ANTHROPIC_API_KEY` and `ONLINE_TOKEN` in the dashboard.

## Batch mode

`python3 batch.py` judges a 30-company × 3-quarter FY26 demo dataset
(directional approximations, not verified actuals) and writes
`batch_results.md` — 90 verdicts with anthems. Good for stress-testing the
mood rules and the songbank's range.

## Files

| File | Role |
|---|---|
| `maestro.py` | CLI conductor — judge then render |
| `judge.py` | Fable 5 + web search analyst (or `--offline` rules) |
| `synth.py` | Four-movement synthesizer (verdict-aware) |
| `songpick.py` + `songbank.json` | Anthem matcher (~100 songs) |
| `app.py` + `render.yaml` | Web app / Render deployment |
| `batch.py` | 90-instance batch demo run |
| `symphony.py` | v1 standalone (rules-only, kept for reference) |
| `examples/` | Three archetypes: compounder, J-curve, gross-revenue illusion |
