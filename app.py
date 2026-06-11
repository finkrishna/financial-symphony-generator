#!/usr/bin/env python3
"""
app.py — the Financial Symphony Generator as a small web thing.

A tribute to Douglas Adams: feed it a quarter, it tells you the mood,
the grade, and — most importantly — the song. DON'T PANIC.

Public path uses the free offline judge. The online judge (Fable 5 + web
search, costs real money) is gated behind ONLINE_TOKEN.
"""

import glob
import json
import os
import time
import uuid

from flask import Flask, jsonify, request, send_file

import judge as judge_mod
import songpick
import synth
import yfetch

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # quarterly results are small

WAV_DIR = "/tmp/symphony_wavs"
os.makedirs(WAV_DIR, exist_ok=True)

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "examples")


def validate(d):
    if not isinstance(d, dict):
        return "payload must be a JSON object"
    for key in ("revenue", "ebitda_margin"):
        v = d.get(key)
        if (not isinstance(v, list) or not 5 <= len(v) <= 16
                or not all(isinstance(x, (int, float)) for x in v)):
            return f"'{key}' must be a list of 5-16 numbers (oldest first)"
    if len(d["revenue"]) != len(d["ebitda_margin"]):
        return "'revenue' and 'ebitda_margin' must be the same length"
    if any(r <= 0 for r in d["revenue"]):
        return "'revenue' values must be positive"
    for key, lo, hi in (("net_debt_to_ebitda", -5, 50), ("ocf_to_ebitda", -2, 3),
                        ("eps_surprise_pct", -5, 5)):
        if key in d and not (isinstance(d[key], (int, float)) and lo <= d[key] <= hi):
            return f"'{key}' must be a number in [{lo}, {hi}]"
    return None


def sweep_old_wavs(max_age_sec=3600):
    now = time.time()
    for f in glob.glob(os.path.join(WAV_DIR, "*.wav")):
        if now - os.path.getmtime(f) > max_age_sec:
            try:
                os.remove(f)
            except OSError:
                pass


@app.get("/health")
def health():
    with open(songpick.BANK_PATH) as f:
        n = len(json.load(f)["songs"])
    return jsonify({"status": "mostly harmless", "songs": n})


@app.get("/examples")
def examples():
    out = {}
    for path in sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.json"))):
        with open(path) as f:
            out[os.path.splitext(os.path.basename(path))[0]] = json.load(f)
    return jsonify(out)


@app.get("/fetch/<symbol>")
def fetch_ticker(symbol):
    try:
        return jsonify(yfetch.fetch(symbol))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"fetch failed: {e}"}), 502


@app.post("/judge")
def judge_endpoint():
    body = request.get_json(silent=True) or {}
    d = body.get("data")
    err = validate(d)
    if err:
        return jsonify({"error": err}), 400

    online = bool(body.get("online"))
    if online:
        token = os.environ.get("ONLINE_TOKEN")
        if not token or body.get("token") != token:
            return jsonify({"error": "online judge is token-gated (it costs real money). "
                                     "Omit 'online' for the free rules judge."}), 403

    try:
        verdict = judge_mod.judge(d, offline=not online, verbose=False)
    except Exception as e:
        return jsonify({"error": f"judge failed: {e}"}), 502

    company = str(d.get("company", "Company"))[:80]
    quarter = str(d.get("quarter", "Q?"))[:20]
    lang = body.get("lang") if body.get("lang") in ("hi", "en") else None
    song, runners = songpick.pick(verdict, company, quarter, lang=lang)

    sweep_old_wavs()
    wav_id = uuid.uuid4().hex
    info = synth.render(d, verdict, os.path.join(WAV_DIR, f"{wav_id}.wav"))

    return jsonify({
        "company": company, "quarter": quarter,
        "verdict": verdict,
        "anthem": {**song, "youtube": songpick.youtube_url(song)},
        "runners_up": [{**s, "youtube": songpick.youtube_url(s)} for s in runners],
        "symphony": {"wav": f"/wav/{wav_id}", "bpm": info["bpm"], "key": info["key"],
                     "cadence": info["cadence"], "detune_cents": info["detune"],
                     "seconds": round(info["seconds"])},
        "judge": "fable-5-online" if online else "offline-rules",
    })


@app.get("/wav/<wav_id>")
def wav(wav_id):
    if not (len(wav_id) == 32 and all(c in "0123456789abcdef" for c in wav_id)):
        return jsonify({"error": "no such symphony"}), 404
    path = os.path.join(WAV_DIR, f"{wav_id}.wav")
    if not os.path.exists(path):
        return jsonify({"error": "this symphony has been swept away, like so much else"}), 404
    return send_file(path, mimetype="audio/wav")


PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Financial Symphony Generator — there's a song for this</title>
<style>
  :root { --bg:#101418; --panel:#1a2128; --ink:#d7e0e8; --dim:#7d8b99; --acc:#5dd39e; --warn:#e8a87c; }
  * { box-sizing:border-box; }
  body { background:var(--bg); color:var(--ink); font:16px/1.55 "Georgia", serif; margin:0; padding:2rem 1rem 4rem; }
  main { max-width:780px; margin:0 auto; }
  h1 { font-size:1.7rem; margin:0 0 .2rem; }
  .panic { color:var(--acc); font-size:.85rem; letter-spacing:.25em; }
  .sub { color:var(--dim); margin:.3rem 0 1.6rem; }
  .panel { background:var(--panel); border-radius:10px; padding:1.2rem; margin-bottom:1.2rem; }
  textarea { width:100%; height:200px; background:#0c1014; color:var(--ink); border:1px solid #2c3640;
             border-radius:6px; padding:.7rem; font:13px/1.5 ui-monospace, monospace; }
  button { background:var(--acc); color:#08110c; border:0; border-radius:6px; padding:.55rem 1.1rem;
           font-weight:bold; cursor:pointer; margin:.3rem .4rem .3rem 0; }
  button.ghost { background:#26303a; color:var(--ink); font-weight:normal; }
  select { background:#26303a; color:var(--ink); border:0; border-radius:6px; padding:.5rem; }
  .grade { font-size:2.6rem; color:var(--acc); }
  .mood { text-transform:uppercase; letter-spacing:.15em; color:var(--warn); }
  .flag { color:var(--warn); }
  .why { color:var(--dim); font-style:italic; }
  a { color:var(--acc); }
  .bar { color:var(--acc); font-family:ui-monospace, monospace; }
  footer { color:var(--dim); font-size:.8rem; margin-top:2.5rem; text-align:center; }
  #out { display:none; }
  .tribute { display:flex; gap:1rem; align-items:flex-start; }
  .tribute img { border-radius:8px; width:110px; }
  .tribute blockquote { margin:0 0 .4rem; font-style:italic; cursor:pointer; }
  .tribute cite { color:var(--dim); font-size:.85rem; }
  .dnaname { color:var(--dim); font-size:.8rem; margin-top:.6rem; }
  .marvin { margin:0; width:130px; flex-shrink:0; }
  .marvin img { width:130px; }
  .marvin figcaption { color:var(--dim); font-size:.7rem; font-style:italic; }
  .ytwrap { position:relative; width:100%; aspect-ratio:16/9; margin:.6rem 0; }
  .ytwrap iframe { position:absolute; inset:0; width:100%; height:100%; border:0; border-radius:8px; }
  @media (max-width:640px) { .tribute { flex-wrap:wrap; } }
</style></head><body><main>
<h1>🎼 Financial Symphony Generator</h1>
<div class="panic">DON'T PANIC</div>
<p class="sub">Feed it a quarterly result. A disciplined-analyst rules engine judges it —
then tells you <em>the song</em>. Largely harmless.</p>

<div class="panel tribute">
  <img id="dna" src="https://upload.wikimedia.org/wikipedia/commons/thumb/c/c0/Douglas_adams_portrait_cropped.jpg/250px-Douglas_adams_portrait_cropped.jpg"
       alt="Douglas Adams" title="Douglas Adams, 1952–2001">
  <div>
    <blockquote id="quote" onclick="nextQuote()" title="click for another"></blockquote>
    <cite id="qsource"></cite>
    <div class="dnaname">Douglas Adams, 1952–2001 — who knew exactly which pieces of paper were unhappy.</div>
  </div>
  <figure class="marvin">
    <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/C2E2_2015_-_Marvin_the_Paranoid_Android_%2817306748285%29.jpg/250px-C2E2_2015_-_Marvin_the_Paranoid_Android_%2817306748285%29.jpg"
         alt="Marvin the Paranoid Android (cosplay)">
    <figcaption>Marvin (artist's impression — the studio owns the real one).
    Here I am, brain the size of a planet, and they ask me to rate quarterly results.</figcaption>
  </figure>
</div>

<div class="panel">
  <div style="margin-bottom:.7rem">
    <input id="ticker" placeholder="NSE/BSE ticker, e.g. RELIANCE, GIPCL, ETERNAL"
           style="background:#0c1014;color:var(--ink);border:1px solid #2c3640;border-radius:6px;padding:.55rem;width:60%"
           onkeydown="if(event.key==='Enter')fetchTicker()">
    <button onclick="fetchTicker()">Fetch &amp; judge</button>
  </div>
  <div id="exbtns">Loading archetypes…</div>
  <textarea id="payload" spellcheck="false"></textarea>
  <div style="margin-top:.6rem">
    <select id="lang"><option value="">any language</option>
      <option value="hi">Hindi anthem</option><option value="en">English anthem</option></select>
    <button onclick="judge()">Judge this quarter</button>
    <span id="busy" style="display:none;color:var(--dim)">consulting Deep Thought…</span>
  </div>
</div>

<div class="panel" id="out">
  <div><span class="grade" id="grade"></span> &nbsp; <span class="mood" id="mood"></span>
       <span style="color:var(--dim)" id="intensity"></span></div>
  <p id="headline"></p>
  <div class="bar" id="scores"></div>
  <ul id="evidence"></ul>
  <div id="flags"></div>
  <hr style="border-color:#2c3640">
  <h3 style="margin:.4rem 0">🎵 This quarter's anthem</h3>
  <div id="song"></div>
  <div class="why" id="why"></div>
  <div class="ytwrap"><iframe id="yt" title="anthem player" allowfullscreen
       allow="encrypted-media; picture-in-picture" referrerpolicy="strict-origin-when-cross-origin"></iframe></div>
  <div id="runners" style="color:var(--dim);font-size:.9rem;margin-top:.4rem"></div>
  <h3 style="margin:1rem 0 .4rem">🎻 B-side: the quarter itself, synthesized</h3>
  <audio id="player" controls style="width:100%"></audio>
  <div style="color:var(--dim);font-size:.85rem" id="synthinfo"></div>
</div>

<footer>Share and Enjoy — a tribute to Douglas Adams from the Complaints Division of the
Sirius Cybernetics Corporation.<br>Offline rules judge: free, instant, sees no peers.
The full Fable&nbsp;5 judge exists but costs real money, so it answers only to the keeper of the token.<br>
Photos: <a href="https://commons.wikimedia.org/wiki/File:Douglas_adams_portrait_cropped.jpg">Douglas Adams</a>
by Michael Hughes, <a href="https://commons.wikimedia.org/wiki/File:C2E2_2015_-_Marvin_the_Paranoid_Android_(17306748285).jpg">Marvin cosplay</a>
by GabboT — both CC BY-SA 2.0, via Wikimedia Commons.</footer>
</main>
<script>
const QUOTES = [
  ["Most of the people were unhappy for pretty much of the time. Many solutions were suggested... but most of these were largely concerned with the movements of small green pieces of paper, which is odd because on the whole it wasn't the small green pieces of paper that were unhappy.", "The Hitchhiker's Guide to the Galaxy"],
  ["I love deadlines. I love the whooshing noise they make as they go by.", "The Salmon of Doubt — also every guidance call, ever"],
  ["The ships hung in the sky in much the same way that bricks don't.", "The Hitchhiker's Guide to the Galaxy"],
  ["The Answer to the Great Question of Life, the Universe and Everything is... Forty-two.", "Deep Thought, after 7.5 million years — still faster than some audit committees"],
  ["In the beginning the Universe was created. This has made a lot of people very angry and been widely regarded as a bad move.", "The Restaurant at the End of the Universe"],
  ["We demand rigidly defined areas of doubt and uncertainty!", "the philosophers' union — and every sell-side disclaimer"],
  ["A common mistake that people make when trying to design something completely foolproof is to underestimate the ingenuity of complete fools.", "Mostly Harmless"],
  ["Time is an illusion. Lunchtime doubly so.", "The Hitchhiker's Guide to the Galaxy"]
];
let qi = Math.floor(Math.random() * QUOTES.length);
function showQuote() {
  document.getElementById('quote').textContent = '“' + QUOTES[qi][0] + '”';
  document.getElementById('qsource').textContent = '— ' + QUOTES[qi][1];
}
function nextQuote() { qi = (qi + 1) % QUOTES.length; showQuote(); }
showQuote();

let EX = {};
fetch('/examples').then(r=>r.json()).then(ex => {
  EX = ex;
  const div = document.getElementById('exbtns'); div.innerHTML = '';
  for (const name of Object.keys(ex)) {
    const b = document.createElement('button'); b.className = 'ghost';
    b.textContent = name.replaceAll('_',' ');
    b.onclick = () => document.getElementById('payload').value = JSON.stringify(ex[name], null, 2);
    div.appendChild(b);
  }
  document.getElementById('payload').value = JSON.stringify(ex[Object.keys(ex)[0]], null, 2);
});
async function fetchTicker() {
  const t = document.getElementById('ticker').value.trim();
  if (!t) return;
  document.getElementById('busy').style.display = 'inline';
  const r = await fetch('/fetch/' + encodeURIComponent(t));
  const j = await r.json();
  document.getElementById('busy').style.display = 'none';
  if (j.error) { alert(j.error); return; }
  document.getElementById('payload').value = JSON.stringify(j, null, 2);
  judge();
}
async function judge() {
  let d; try { d = JSON.parse(document.getElementById('payload').value); }
  catch { alert('That is not JSON. This must be Thursday.'); return; }
  document.getElementById('busy').style.display = 'inline';
  const r = await fetch('/judge', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({data:d, lang:document.getElementById('lang').value || undefined})});
  const j = await r.json();
  document.getElementById('busy').style.display = 'none';
  if (j.error) { alert(j.error); return; }
  const v = j.verdict;
  document.getElementById('out').style.display = 'block';
  document.getElementById('grade').textContent = v.grade;
  document.getElementById('mood').textContent = v.mood.replaceAll('_',' ');
  document.getElementById('intensity').textContent = ' intensity ' + v.intensity.toFixed(2);
  document.getElementById('headline').textContent = v.headline;
  document.getElementById('scores').textContent = Object.entries(v.scores)
    .map(([k,s]) => k.replaceAll('_',' ') + ' ' + '█'.repeat(s) + '·'.repeat(10-s)).join('   ');
  document.getElementById('evidence').innerHTML = v.key_evidence.map(e=>'<li>'+e+'</li>').join('');
  document.getElementById('flags').innerHTML = v.red_flags.map(f=>'<div class="flag">⚠ '+f+'</div>').join('');
  document.getElementById('song').innerHTML = '«' + j.anthem.title + '» — ' + j.anthem.artist +
    ' (' + j.anthem.era + ') &nbsp; <a target="_blank" href="' + j.anthem.youtube + '">open on YouTube</a>';
  document.getElementById('why').textContent = j.anthem.why_it_fits;
  // embedded YouTube search-playlist: plays the actual song via YouTube's
  // own player and licenses — the legal way to "play it directly"
  document.getElementById('yt').src = 'https://www.youtube.com/embed?listType=search&list=' +
    encodeURIComponent(j.anthem.title + ' ' + j.anthem.artist);
  document.getElementById('runners').innerHTML = j.runners_up.length ?
    'Also considered: ' + j.runners_up.map(s=>'«'+s.title+'» ('+s.artist+')').join('; ') : '';
  document.getElementById('player').src = j.symphony.wav;
  document.getElementById('synthinfo').textContent = j.symphony.seconds + 's, ' + j.symphony.bpm +
    ' bpm, ' + j.symphony.key + ', ' + j.symphony.cadence + ' cadence' +
    (j.symphony.detune_cents ? ', detuned ' + j.symphony.detune_cents + '¢ (the accounts sound almost right)' : '');
}
</script></body></html>"""


@app.get("/")
def index():
    return PAGE


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5050)), debug=False)
