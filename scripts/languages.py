#!/usr/bin/env python3
"""Draw the "Most used languages" card for the profile README.

Reads the languages of every repository the token can see, adds up their
bytes and writes assets/languages-dark.svg and assets/languages-light.svg.
Only the Python standard library is used.

The look follows the Ficelle style: warm neutrals, one small corner, 1px
border, no shadow, Hanken Grotesk, and tag colours as 6px square marks.
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "fonts" / "HankenGrotesk-subset.woff2"
OUT = ROOT / "assets"

OWNER = os.environ.get("OWNER", "Synaelle")
TOKEN = os.environ.get("GH_TOKEN", "")

# Settings
SHOWN = 5            # languages listed before the rest becomes "Other"
HIDE = set()         # languages to leave out, like {"HTML", "CSS"}
SKIP = set()         # repositories to leave out, like {"synaweb"}
TITLE = "Most used languages"

# Ficelle tokens
THEMES = {
    "dark": {"surface": "#161414", "border": "#2E2A28", "text": "#E6DFD8", "muted": "#9A918A"},
    "light": {"surface": "#FBFAF7", "border": "#CBC6BC", "text": "#161413", "muted": "#5E5853"},
}
MARKS = ["#C2564A", "#C49A3C", "#7D9E68", "#6A93C4", "#9B82C6"]  # tag-red to tag-purple

WIDTH = 340
PAD = 16
BAR_Y, BAR_H = 44, 8
ROW_Y, ROW_H = 76, 22


def get(url):
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "profile-languages",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def pages(url):
    page = 1
    while True:
        batch = get(f"{url}{'&' if '?' in url else '?'}per_page=100&page={page}")
        yield from batch
        if len(batch) < 100:
            return
        page += 1


def repositories():
    """Private ones too when the token is a personal one, public ones otherwise."""
    try:
        return list(pages("https://api.github.com/user/repos?affiliation=owner"))
    except urllib.error.HTTPError as error:
        if error.code not in (401, 403, 404):
            raise
        return list(pages(f"https://api.github.com/users/{OWNER}/repos?type=owner"))


def fetch():
    totals = {}
    for repo in repositories():
        if repo["fork"] or repo["name"] in SKIP or repo["owner"]["login"].lower() != OWNER.lower():
            continue
        for language, size in get(repo["languages_url"]).items():
            totals[language] = totals.get(language, 0) + size
    return totals


def shares(totals):
    """[(name, percent)] for the top languages, then Other for what is left."""
    kept = sorted(((n, s) for n, s in totals.items() if n not in HIDE and s > 0),
                  key=lambda item: -item[1])
    total = sum(size for _, size in kept)
    if not total:
        sys.exit("no languages found")
    rows = [(name, 100 * size / total) for name, size in kept[:SHOWN]]
    rest = 100 - sum(percent for _, percent in rows)
    if len(kept) > SHOWN and rest > 0:
        rows.append(("Other", rest))
    return rows


def render(rows, theme, font):
    c = THEMES[theme]
    colours = [MARKS[i] if name != "Other" else c["muted"] for i, (name, _) in enumerate(rows)]
    half = (len(rows) + 1) // 2
    height = ROW_Y + half * ROW_H + 4
    inner = WIDTH - 2 * PAD

    bar, x = [], float(PAD)
    for (name, percent), colour in zip(rows, colours):
        w = max(inner * percent / 100, 2)
        w = min(w, PAD + inner - x)
        if w > 0:
            bar.append(f'<rect x="{x:.2f}" y="{BAR_Y}" width="{w:.2f}" height="{BAR_H}" fill="{colour}"/>')
        x += w

    legend = []
    for i, ((name, percent), colour) in enumerate(zip(rows, colours)):
        lx = PAD + (i // half) * (inner / 2 + 4)
        ly = ROW_Y + (i % half) * ROW_H
        label = f"{percent:.1f}%" if percent >= 0.1 else "&lt;0.1%"
        legend.append(
            f'<rect x="{lx:.0f}" y="{ly}" width="6" height="6" fill="{colour}"/>'
            f'<text x="{lx + 14:.0f}" y="{ly + 8}" class="row">{escape(name)}'
            f'<tspan class="meta" dx="6">{label}</tspan></text>'
        )

    summary = ", ".join(f"{name} {percent:.1f}%" for name, percent in rows)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="t d">
<title id="t">{escape(TITLE)}</title>
<desc id="d">{escape(summary)}</desc>
<style>
@font-face {{ font-family: "Hanken Grotesk"; font-weight: 100 900; src: url(data:font/woff2;base64,{font}) format("woff2"); }}
text {{ font-family: "Hanken Grotesk", system-ui, sans-serif; fill: {c["text"]}; }}
.title {{ font-size: 14px; font-weight: 600; }}
.row {{ font-size: 13px; font-weight: 400; }}
.meta {{ font-size: 12px; fill: {c["muted"]}; }}
</style>
<clipPath id="bar"><rect x="{PAD}" y="{BAR_Y}" width="{inner}" height="{BAR_H}" rx="2"/></clipPath>
<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="2" fill="{c["surface"]}" stroke="{c["border"]}"/>
<text x="{PAD}" y="30" class="title">{escape(TITLE)}</text>
<g clip-path="url(#bar)">{"".join(bar)}</g>
{"".join(legend)}
</svg>
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-json", help="a file of {language: bytes}, to draw without the API")
    args = parser.parse_args()

    totals = json.loads(Path(args.from_json).read_text()) if args.from_json else fetch()
    rows = shares(totals)
    font = base64.b64encode(FONT.read_bytes()).decode()
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"languages-{theme}.svg").write_text(render(rows, theme, font), encoding="utf-8")
    print(", ".join(f"{name} {percent:.1f}%" for name, percent in rows))


if __name__ == "__main__":
    main()
