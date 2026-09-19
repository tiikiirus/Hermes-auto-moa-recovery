#!/usr/bin/env python3
"""Fixture tests for slopcheck. Run: python3 tests/test_slopcheck.py"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, "scripts"))

from slopcheck import analyze  # noqa: E402
from sanitize import scan  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


def check(label, condition, detail=""):
    print("{:4}  {}{}".format("ok" if condition else "FAIL", label,
                              "  ({})".format(detail) if detail else ""))
    return condition


def main():
    ok = True

    slop = analyze(load("slop.md"))
    ok &= check("slop fixture fails the gate", not slop["passed"])
    ok &= check("slop fixture scores at or below 20", slop["score"] <= 20,
                "{}".format(slop["score"]))
    for rid in ["W1", "W2", "W6", "S2", "S3", "S4", "S13", "F1"]:
        ok &= check("slop fixture flags {}".format(rid),
                    any(f["rule"] == rid for f in slop["findings"]))

    clean = analyze(load("clean.md"))
    ok &= check("clean fixture passes the gate", clean["passed"])
    ok &= check("clean fixture scores at or above 95", clean["score"] >= 95,
                "{}".format(clean["score"]))

    mask = analyze(load("masking.md"))
    rules = {f["rule"] for f in mask["findings"]}
    lines = {f["line"] for f in mask["findings"]}
    ok &= check("code, quotes, frontmatter and URLs are masked", len(mask["findings"]) == 2,
                "{} findings: {}".format(len(mask["findings"]), sorted(rules)))
    ok &= check("slop-ignore suppresses its line", 20 not in lines)
    ok &= check("line numbers are not off by one", 22 in lines)

    scores = {analyze(load("slop.md"))["score"] for _ in range(3)}
    ok &= check("scoring is deterministic", len(scores) == 1)

    raw = load("watermarked.md")
    wm = analyze(raw)
    ok &= check("watermarked fixture is blocked by the gate",
                not wm["passed"] and "U1" in wm["blocking"])

    cleaned, hits = scan(raw)
    removed = [h for h in hits if h["action"] == "removed"]
    ok &= check("sanitizer removes zero-width, tag and bidi characters",
                len(removed) >= 3, "{} removed".format(len(removed)))
    for label, seq in [("emoji ZWJ sequence", "\U0001f468\u200d\U0001f469\u200d\U0001f467"),
                       ("emoji variation selector", "\u2764\ufe0f"),
                       ("Devanagari ZWNJ", "\u0915\u094d\u200c\u0937")]:
        ok &= check("sanitizer preserves {}".format(label), seq in cleaned)
    ok &= check("sanitizer output clears the gate", analyze(cleaned)["passed"],
                "{}/100".format(analyze(cleaned)["score"]))
    ok &= check("sanitizer is idempotent", scan(cleaned)[0] == cleaned)

    # The skill's own prose has to clear the gate it enforces. patterns.md and
    # lexicon.md are exempt: cataloguing banned words is what they are for.
    root = os.path.join(HERE, os.pardir)
    for name in ["SKILL.md", "references/reviewer.md", "references/voice.md"]:
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            res = analyze(fh.read())
        ok &= check("{} clears its own gate".format(name), res["passed"],
                    "{}/100".format(res["score"]))

    print("\n{}".format("all checks passed" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
