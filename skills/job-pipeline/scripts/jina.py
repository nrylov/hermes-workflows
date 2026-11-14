#!/usr/bin/env python3
"""Read a web page as clean Markdown through Jina Reader (r.jina.ai). Stdlib only.

Usage: jina.py URL [--key-file PATH] [--max-chars N]
The API key comes from $JINA_API_KEY or --key-file. It is never printed or logged.
"""
import argparse
import os
import re
import sys
import urllib.request

READER = "https://r.jina.ai/"


def load_key(key_file=None, env=os.environ):
    key = env.get("JINA_API_KEY")
    if not key and key_file:
        with open(os.path.expanduser(key_file)) as f:
            key = f.read()
    return (key or "").strip() or None


def clean(markdown, max_chars=4000):
    """Drop Jina's Title/URL header, link targets and image syntax; collapse whitespace."""
    text = markdown.split("Markdown Content:", 1)[-1]
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars]


def read_url(url, key=None, timeout=40, opener=urllib.request.urlopen):
    headers = {"Accept": "text/plain", "X-Retain-Images": "none", "User-Agent": "hermes-workflows"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(READER + url, headers=headers)
    with opener(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url")
    ap.add_argument("--key-file")
    ap.add_argument("--max-chars", type=int, default=6000)
    a = ap.parse_args(argv)
    key = load_key(a.key_file)
    if not key:
        print("no Jina key (set JINA_API_KEY or --key-file); trying anonymous", file=sys.stderr)
    try:
        print(clean(read_url(a.url, key), a.max_chars))
    except Exception as exc:
        print("jina read failed: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
