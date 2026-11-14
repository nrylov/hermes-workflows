#!/usr/bin/env python3
"""Fetch RSS/Atom feeds and print recent, unseen items as JSON (stdlib only)."""
import argparse
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

ATOM = "{http://www.w3.org/2005/Atom}"
UA = "hermes-workflows-feed-digest/0.1"


def parse_date(text):
    if not text:
        return None
    text = text.strip()
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def _text(el, tag):
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def parse_feed(xml_bytes, feed_url=""):
    """Return a list of item dicts from RSS 2.0 or Atom XML."""
    root = ET.fromstring(xml_bytes)
    items = []
    if root.tag.endswith("feed"):  # Atom
        feed_title = _text(root, ATOM + "title")
        for e in root.findall(ATOM + "entry"):
            link = ""
            for l in e.findall(ATOM + "link"):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
                    break
            items.append({
                "feed": feed_title or feed_url,
                "title": _text(e, ATOM + "title"),
                "link": link,
                "published": parse_date(_text(e, ATOM + "published") or _text(e, ATOM + "updated")),
                "summary": clean(_text(e, ATOM + "summary"))[:500],
            })
    else:  # RSS
        channel = root.find("channel")
        if channel is None:
            return items
        feed_title = _text(channel, "title")
        for e in channel.findall("item"):
            items.append({
                "feed": feed_title or feed_url,
                "title": _text(e, "title"),
                "link": _text(e, "link"),
                "published": parse_date(_text(e, "pubDate")),
                "summary": clean(_text(e, "description"))[:500],
            })
    return items


def select_items(items, now, hours, seen):
    """Keep items newer than the window (or undated) whose link is not in `seen`."""
    cutoff = now - timedelta(hours=hours)
    out = []
    for it in items:
        key = it["link"] or it["title"]
        if not key or key in seen:
            continue
        if it["published"] is not None and it["published"] < cutoff:
            continue
        out.append(it)
    out.sort(key=lambda i: i["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out


def read_feed_urls(path):
    with open(path) as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("feeds_file")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--seen-file", help="JSON list of already-delivered links; updated in place")
    args = ap.parse_args(argv)

    seen = set()
    if args.seen_file:
        try:
            with open(args.seen_file) as f:
                seen = set(json.load(f))
        except FileNotFoundError:
            pass

    now = datetime.now(timezone.utc)
    results = []
    for url in read_feed_urls(args.feeds_file):
        try:
            results.extend(select_items(parse_feed(fetch(url), url), now, args.hours, seen))
        except Exception as exc:  # one bad feed must not sink the digest
            print("skip %s: %s" % (url, exc), file=sys.stderr)

    results.sort(key=lambda i: i["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for it in results:
        it["published"] = it["published"].isoformat() if it["published"] else None
    if args.seen_file:
        seen.update(i["link"] or i["title"] for i in results)
        with open(args.seen_file, "w") as f:
            json.dump(sorted(seen), f, indent=1)
    json.dump(results, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
