#!/usr/bin/env python3
"""
batch.py — run the offline judge + songpick across a 30-company x 3-quarter
FY26 dataset and emit a markdown table (batch_results.md).

DATA CAVEAT: revenue/margin series are directional approximations of real
companies' trajectories (knowledge through Jan 2026), stylized to 8-quarter
windows — NOT verified actuals. The offline judge sees no peers and no street
expectations. Treat the table as a demo of the pipeline, not research.

Each company: 10 quarters (Q2 FY24 -> Q3 FY26, oldest first) of revenue (Rs cr)
and EBITDA margin, plus per-judged-quarter (ndte, ocf/ebitda, eps_surprise,
one_offs). Three 8-quarter windows are judged: ending Q1, Q2, Q3 FY26.
"""

import json

from judge import judge_offline
from songpick import pick

QUARTERS = ["Q1 FY26", "Q2 FY26", "Q3 FY26"]

# (name, sector, rev[10], margin[10], meta[3] = (net_debt/ebitda, ocf/ebitda, eps_surprise, one_offs))
COMPANIES = [
    ("TCS", "IT Services",
     [59692, 60583, 61237, 62613, 64259, 63973, 64479, 63437, 65799, 66610],
     [.265, .270, .280, .268, .262, .268, .265, .262, .268, .270],
     [(0.0, .95, -.01, False), (0.0, .95, .01, False), (0.0, .95, .005, False)]),
    ("Infosys", "IT Services",
     [38994, 38821, 37923, 39315, 40986, 41764, 40925, 42279, 44490, 44850],
     [.210, .205, .200, .210, .211, .214, .210, .208, .210, .215],
     [(0.0, .95, .02, False), (0.0, .95, .025, False), (0.0, .92, .015, False)]),
    ("Reliance Industries", "Conglomerate",
     [235481, 248160, 240715, 236217, 235481, 244200, 261388, 243632, 259559, 267000],
     [.165, .170, .170, .155, .152, .160, .170, .175, .180, .182],
     [(0.6, .90, .01, False), (0.6, .90, .03, False), (0.55, .90, .04, False)]),
    ("Bharti Airtel", "Telecom",
     [37044, 37900, 37599, 38506, 41473, 45129, 47876, 49463, 52145, 54000],
     [.510, .530, .520, .530, .530, .540, .550, .560, .565, .570],
     [(1.9, .95, .05, False), (1.8, .95, .08, False), (1.7, .95, .06, False)]),
    ("Tata Motors (PV+JLR)", "Auto",
     [105129, 110577, 119986, 108048, 101450, 113575, 119503, 104407, 70000, 95000],
     [.130, .135, .140, .130, .115, .125, .130, .110, .040, .090],
     [(0.5, .85, -.06, False), (0.5, .50, -.80, True), (0.6, .70, -.40, True)]),
    ("Maruti Suzuki", "Auto",
     [37062, 33309, 38235, 35531, 37449, 38492, 40920, 38629, 42300, 44900],
     [.129, .117, .125, .125, .117, .117, .105, .110, .115, .123],
     [(0.0, .90, .02, False), (0.0, .90, .04, False), (0.0, .90, .09, False)]),
    ("Asian Paints", "Paints",
     [8479, 9103, 8731, 8970, 8003, 8549, 8359, 8939, 7800, 8100],
     [.205, .220, .195, .190, .155, .185, .180, .175, .150, .160],
     [(0.0, .85, -.05, False), (0.0, .85, -.08, False), (0.0, .85, -.06, False)]),
    ("Hindustan Unilever", "FMCG",
     [15276, 15188, 15013, 15166, 15703, 15195, 15214, 15747, 15850, 15900],
     [.236, .235, .234, .237, .233, .234, .232, .235, .236, .234],
     [(0.0, .95, .005, False), (0.0, .95, .00, False), (0.0, .95, .01, False)]),
    ("ITC", "FMCG/Tobacco",
     [16550, 17483, 17753, 18220, 20360, 20350, 20376, 19800, 21200, 21300],
     [.360, .370, .365, .360, .355, .350, .345, .350, .345, .350],
     [(0.0, .95, .01, False), (0.0, .95, .015, False), (0.0, .95, .01, False)]),
    ("Titan", "Jewellery/Retail",
     [12529, 13052, 11257, 13266, 14534, 17740, 13477, 14916, 16400, 19200],
     [.105, .100, .095, .100, .094, .092, .090, .095, .092, .094],
     [(0.8, .72, .02, False), (0.8, .72, .01, False), (0.8, .75, .03, False)]),
    ("Avenue Supermarts", "Retail",
     [12624, 13572, 12727, 14069, 14445, 15973, 14872, 16100, 16219, 18800],
     [.080, .085, .075, .088, .079, .081, .072, .083, .072, .077],
     [(0.0, .85, -.03, False), (0.0, .85, -.05, False), (0.0, .85, .02, False)]),
    ("Eternal (Zomato)", "Quick Commerce",
     [2848, 3288, 3562, 4206, 4799, 5405, 5833, 7167, 13590, 16500],
     [.010, .020, .030, .040, .050, .045, .050, .055, .035, .040],
     [(0.0, .55, .05, False), (0.0, .40, .10, True), (0.0, .55, .12, True)]),
    ("One97 (Paytm)", "Fintech",
     [2519, 2851, 2267, 1502, 1660, 1828, 1912, 1918, 2061, 2200],
     [-.180, -.150, -.200, -.350, -.280, -.200, -.100, .020, .050, .080],
     [(0.0, .65, .05, False), (0.0, .65, .04, False), (0.0, .68, .06, False)]),
    ("Nykaa", "Beauty/E-comm",
     [1507, 1789, 1668, 1746, 1875, 2267, 2061, 2155, 2345, 2900],
     [.055, .055, .055, .055, .060, .060, .060, .065, .070, .075],
     [(0.3, .75, .03, False), (0.3, .78, .04, False), (0.3, .82, .06, False)]),
    ("PB Fintech", "Insurtech",
     [812, 871, 1090, 1010, 1167, 1292, 1508, 1348, 1500, 1750],
     [.020, .030, .050, .040, .050, .060, .070, .060, .070, .080],
     [(0.0, .90, .05, False), (0.0, .90, .06, False), (0.0, .90, .08, False)]),
    ("Delhivery", "Logistics",
     [1942, 2194, 2076, 2172, 2190, 2378, 2191, 2294, 2570, 2750],
     [.010, .020, .015, .020, .025, .040, .030, .035, .040, .045],
     [(0.0, .80, .02, False), (0.0, .70, .03, False), (0.0, .75, .04, False)]),
    ("InterGlobe Aviation", "Airlines",
     [14944, 19452, 17825, 19571, 16970, 22111, 22152, 20496, 18555, 23500],
     [.180, .250, .200, .240, .130, .250, .210, .220, .100, .180],
     [(1.5, .90, .03, False), (1.6, .85, -.10, False), (2.0, .80, -.35, True)]),
    ("Vodafone Idea", "Telecom",
     [10600, 10673, 10607, 10508, 10632, 10817, 10914, 10623, 10800, 10300],
     [.400, .410, .410, .420, .420, .430, .440, .410, .420, .400],
     [(12.0, .90, -.05, False), (12.0, .90, -.04, False), (12.0, .90, -.10, False)]),
    ("Tata Steel", "Steel",
     [55682, 55312, 58687, 54771, 53905, 53648, 56218, 53178, 57500, 60200],
     [.080, .115, .110, .120, .110, .120, .135, .140, .150, .155],
     [(2.4, .90, -.02, False), (2.3, .90, .04, False), (2.2, .90, .05, False)]),
    ("JSW Steel", "Steel",
     [44584, 41940, 46269, 42943, 39684, 41378, 44819, 43147, 46300, 48500],
     [.125, .130, .135, .130, .137, .140, .150, .155, .160, .160],
     [(2.8, .85, .02, False), (2.7, .85, .05, False), (2.6, .78, .04, False)]),
    ("UltraTech Cement", "Cement",
     [15635, 16740, 20419, 18069, 15635, 17193, 23063, 21275, 18800, 22700],
     [.160, .170, .180, .180, .185, .190, .195, .200, .200, .205],
     [(1.2, .85, .05, False), (1.2, .78, .02, False), (1.1, .85, .07, False)]),
    ("Sun Pharma", "Pharma",
     [12192, 12381, 11983, 12653, 13292, 13675, 13956, 13954, 14600, 15200],
     [.265, .268, .270, .272, .278, .282, .284, .285, .290, .295],
     [(0.0, .90, .02, False), (0.0, .90, .03, False), (0.0, .90, .02, False)]),
    ("Cipla", "Pharma",
     [6678, 6604, 6163, 6694, 7051, 7073, 6730, 7104, 7400, 7150],
     [.245, .248, .250, .252, .255, .258, .255, .258, .260, .240],
     [(0.0, .90, .02, False), (0.0, .90, .01, False), (0.0, .85, -.08, False)]),
    ("Dixon Technologies", "EMS",
     [4943, 6463, 4658, 6580, 11534, 10454, 10293, 12838, 13500, 12700],
     [.036, .037, .038, .038, .039, .040, .040, .041, .042, .043],
     [(0.5, .80, .06, False), (0.5, .75, .03, False), (0.5, .72, -.05, False)]),
    ("Polycab India", "Cables/FMEG",
     [4253, 4341, 5592, 4698, 5498, 5226, 6986, 5906, 6300, 6800],
     [.125, .127, .130, .130, .132, .133, .135, .138, .140, .142],
     [(0.0, .85, .04, False), (0.0, .85, .03, False), (0.0, .85, .06, False)]),
    ("Suzlon Energy", "Wind Energy",
     [1417, 1553, 2207, 2016, 2093, 2969, 3825, 3117, 3300, 4100],
     [.140, .145, .150, .152, .155, .160, .165, .168, .170, .175],
     [(0.0, .80, .05, False), (0.0, .82, .06, False), (0.0, .85, .08, False)]),
    ("GIPCL", "Power Utility",
     [425, 398, 380, 410, 442, 405, 390, 430, 455, 470],
     [.300, .300, .305, .310, .310, .315, .315, .320, .325, .330],
     [(0.0, .95, .02, False), (0.0, .95, .03, False), (0.0, .95, .05, False)]),
    ("NTPC", "Power Utility",
     [44983, 47574, 47622, 48982, 45385, 47057, 49834, 49645, 46500, 48900],
     [.280, .282, .284, .286, .288, .290, .292, .294, .296, .298],
     [(3.6, .90, .01, False), (3.6, .90, .01, False), (3.6, .90, .02, False)]),
    ("Adani Power", "Power Utility",
     [12991, 13355, 13787, 14956, 13339, 13671, 14237, 14700, 14600, 15300],
     [.360, .362, .365, .368, .370, .372, .375, .378, .380, .385],
     [(1.8, .85, .03, False), (1.8, .85, .02, False), (1.7, .85, .04, False)]),
    ("Trent", "Retail/Fashion",
     [2853, 3467, 3298, 4104, 4157, 4657, 4334, 4734, 4800, 5500],
     [.155, .158, .160, .162, .165, .168, .170, .172, .170, .175],
     [(0.5, .80, -.18, False), (0.5, .75, -.10, False), (0.5, .80, .02, False)]),
]


def brief(d, verdict):
    rev, margins = d["revenue"], d["ebitda_margin"]
    yoy = rev[-1] / rev[-5] - 1
    trend = margins[-1] - margins[0]
    flags = "⚠ " + "; ".join(verdict["red_flags"]) if verdict["red_flags"] else "No red flags."
    return (
        f"Rev ₹{rev[-1]:,} cr, YoY {yoy:+.1%}; EBITDA margin {margins[-1]:.1%} ({trend * 100:+.1f}pp over 8q).<br>"
        f"OCF/EBITDA {d['ocf_to_ebitda']:.0%}, net debt {d['net_debt_to_ebitda']:.1f}× EBITDA, EPS surprise {d['eps_surprise_pct']:+.0%}"
        f"{', one-offs present' if d['one_off_items'] else ''}.<br>"
        f"{flags}"
    )


def main():
    rows, mood_count = [], {}
    for name, sector, rev10, mgn10, metas in COMPANIES:
        assert len(rev10) == 10 and len(mgn10) == 10 and len(metas) == 3, name
        for i, q in enumerate(QUARTERS):
            ndte, ocf, surp, one_offs = metas[i]
            d = {
                "company": name, "quarter": q,
                "revenue": rev10[i:i + 8], "ebitda_margin": mgn10[i:i + 8],
                "net_debt_to_ebitda": ndte, "ocf_to_ebitda": ocf,
                "eps_surprise_pct": surp, "one_off_items": one_offs,
            }
            v = judge_offline(d)
            song, _ = pick(v, company=name, quarter=q)
            mood_count[v["mood"]] = mood_count.get(v["mood"], 0) + 1
            rows.append((name, sector, q, v, brief(d, v), song))

    lines = [
        "# FY26 batch run — offline judge + songbank (100 songs)",
        "",
        "*Figures are directional approximations (knowledge cutoff Jan 2026), not verified actuals.*",
        "*Offline rules judge: no peer or street-expectation context. Rerun any row online for the full verdict.*",
        "",
        "| # | Company | Qtr | Mood | Grade | Analysis | Anthem |",
        "|---|---------|-----|------|-------|----------|--------|",
    ]
    for n, (name, sector, q, v, b, song) in enumerate(rows, 1):
        anthem = f"«{song['title']}» — {song['artist']}<br><em>{song['why_it_fits']}</em>"
        lines.append(f"| {n} | {name} | {q} | {v['mood']} | {v['grade']} | {b} | {anthem} |")

    lines += ["", "## Mood distribution", ""]
    lines += [f"- **{m}**: {c}" for m, c in sorted(mood_count.items(), key=lambda x: -x[1])]

    out = "\n".join(lines) + "\n"
    with open("batch_results.md", "w") as f:
        f.write(out)
    print(out)
    print(f"\n{len(rows)} instances judged. Written to batch_results.md")


if __name__ == "__main__":
    main()
