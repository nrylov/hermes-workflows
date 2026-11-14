#!/usr/bin/env python3
"""Check every skills/*/SKILL.md for required frontmatter and a short description."""
import glob
import re
import sys

REQUIRED = ["name", "description", "version", "author", "license", "platforms"]
bad = 0
for path in sorted(glob.glob("skills/*/SKILL.md")):
    text = open(path).read()
    m = re.match(r"---\n(.*?)\n---\n(.+)", text, re.S)
    if not m:
        print("FAIL %s: no frontmatter/body" % path); bad += 1; continue
    fm = dict(re.findall(r"^(\w+):\s*(.*)$", m.group(1), re.M))
    miss = [k for k in REQUIRED if k not in fm]
    desc = fm.get("description", "")
    if miss or len(desc) > 60 or not desc.endswith("."):
        print("FAIL %s: missing=%s desc_len=%d" % (path, miss, len(desc))); bad += 1
    else:
        print("ok   %s" % path)
sys.exit(1 if bad else 0)
