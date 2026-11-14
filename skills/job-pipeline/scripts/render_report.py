#!/usr/bin/env python3
"""Render tracker.csv as a self-contained HTML report (filter, search, sort by score).

Usage: render_report.py TRACKER.csv OUT.html [--min-score N] [--limit N]
Designed for the Hermes desktop preview widget: uses the app's theme variables and no
external assets. Each row has a button that asks the agent for tailored talking points.
"""
import argparse
import csv
import json
import sys

TEMPLATE = """<style>
.jp{font-size:13px;color:var(--foreground)}
.jp .bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center}
.jp input,.jp select{background:var(--card);color:var(--foreground);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font:inherit}
.jp table{border-collapse:collapse;width:100%}
.jp th,.jp td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);vertical-align:top}
.jp th{color:var(--muted-foreground);font-weight:500;cursor:pointer;white-space:nowrap}
.jp .s{font-weight:600;text-align:center;border-radius:6px;padding:2px 7px;display:inline-block;min-width:18px}
.jp .s5,.jp .s4{background:var(--accent);color:var(--accent-foreground,var(--foreground))}
.jp .s3,.jp .s2,.jp .s1{border:1px solid var(--border);color:var(--muted-foreground)}
.jp .why{color:var(--muted-foreground)}
.jp a{color:var(--accent)}
.jp button{font:inherit;background:none;color:var(--accent);border:1px solid var(--border);border-radius:6px;padding:2px 8px;cursor:pointer}
.jp .n{color:var(--muted-foreground);margin:6px 0}
</style>
<div class="jp">
 <div class="bar">
  <input id="q" placeholder="Search company, title, reason" size="32">
  <select id="min"><option value="1">All scores</option><option value="3">3+</option><option value="4" selected>4+</option><option value="5">5 only</option></select>
  <select id="co"><option value="">All companies</option></select>
 </div>
 <div class="n" id="count"></div>
 <table><thead><tr><th data-k="score">Score</th><th data-k="company">Company</th><th data-k="title">Role</th><th data-k="location">Location</th><th>Why</th><th></th></tr></thead><tbody id="rows"></tbody></table>
</div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id);
let key="score",dir=-1;
const cos=[...new Set(D.map(r=>r.company))].sort();
cos.forEach(c=>{const o=document.createElement("option");o.value=c;o.textContent=c;$("co").appendChild(o)});
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function draw(){
 const q=$("q").value.toLowerCase(),m=+$("min").value,c=$("co").value;
 const rows=D.filter(r=>r.score>=m&&(!c||r.company===c)&&(!q||(r.company+r.title+r.reason).toLowerCase().includes(q)))
  .sort((a,b)=>(a[key]>b[key]?1:a[key]<b[key]?-1:0)*dir);
 $("count").textContent=rows.length+" of "+D.length+" postings";
 $("rows").innerHTML=rows.map(r=>`<tr><td><span class="s s${r.score}">${r.score}</span></td><td>${esc(r.company)}</td>
 <td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a></td><td>${esc(r.location.split("|")[0])}</td>
 <td class="why">${esc(r.reason)}</td>
 <td><button data-hermes-send="Using the job-pipeline skill and my private profile, draft tailored talking points for this posting: ${esc(r.company)} - ${esc(r.title)} (${esc(r.url)}). Use only facts in my profile.">Talking points</button></td></tr>`).join("");
}
["q","min","co"].forEach(i=>$(i).addEventListener("input",draw));
document.querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{const k=th.dataset.k;dir=(k===key)?-dir:(k==="score"?-1:1);key=k;draw()});
draw();
</script>
"""


def load_rows(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        try:
            r["score"] = int(r.get("score") or 0)
        except ValueError:
            r["score"] = 0
    return rows


def render(rows, min_score=1, limit=None):
    rows = [r for r in rows if r["score"] >= min_score]
    rows.sort(key=lambda r: -r["score"])
    if limit:
        rows = rows[:limit]
    keep = ["id", "company", "title", "location", "url", "score", "reason", "status"]
    data = [{k: r.get(k, "") for k in keep} for r in rows]
    # "</" must not appear inside a <script> block
    payload = json.dumps(data).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", payload)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tracker")
    ap.add_argument("out")
    ap.add_argument("--min-score", type=int, default=1)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    html_out = render(load_rows(a.tracker), a.min_score, a.limit)
    with open(a.out, "w") as f:
        f.write(html_out)
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
