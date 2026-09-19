#!/usr/bin/env python3
"""Optional third-party AI-detector check. Zero dependencies.

This sends the draft to an outside service. Do not run it on anything you are not
allowed to share, such as unpublished customer material, without permission.

Treat the result as one signal, never as the gate. Detectors disagree with each
other, flag human writing, and drift as the vendor retrains. A draft tuned until
one detector goes quiet tends to read worse to people, which is the audience that
matters. The per-sentence scores are the useful part: they point at lines worth
rereading.

Usage:
    python3 detect.py --setup --key-from keychain:sapling
    python3 detect.py DRAFT.md
    python3 detect.py DRAFT.md --threshold 0.3 --json

Supported detectors: sapling (https://sapling.ai/docs/api/detector/).
Exit codes: 0 = at or under threshold, 1 = over threshold, 2 = setup or API error.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import credentials  # noqa: E402


def sapling(text, timeout, key):
    body = json.dumps({"key": key, "text": text, "sent_scores": True}).encode("utf-8")
    req = urllib.request.Request("https://api.sapling.ai/api/v1/aidetect", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    sentences = []
    for item in data.get("sentence_scores") or []:
        if isinstance(item, dict) and "score" in item:
            sentences.append({"score": float(item["score"]),
                              "sentence": str(item.get("sentence", "")).strip()})
    # Sapling: 0 is maximum confidence human-written, 1 is maximum confidence AI.
    return {"score": float(data["score"]), "sentences": sentences}


DETECTORS = {"sapling": sapling}


def prose_only(text):
    """Send prose, not code, frontmatter, or URLs, which skew every detector."""
    from slopcheck import mask_regions
    return "\n".join(line.rstrip() for line in mask_regions(text).split("\n"))


def main():
    ap = argparse.ArgumentParser(description="Optional third-party AI-detector check.")
    ap.add_argument("path", nargs="?")
    ap.add_argument("--key-from",
                    help="Where the detector key lives: env:NAME, keychain:SERVICE, file:PATH, or op://...")
    ap.add_argument("--setup", action="store_true",
                    help="Verify --key-from and save the location for later runs.")
    ap.add_argument("--detector", choices=sorted(DETECTORS), default="sapling")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="Fail above this AI probability, 0 to 1.")
    ap.add_argument("--top", type=int, default=5, help="How many high-scoring sentences to list.")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        saved = credentials.load_config()
        key_from = args.key_from or saved.get("detector", {}).get("key_from")
        if args.setup:
            if not args.key_from:
                sys.stderr.write("--setup needs --key-from\n")
                return 2
            credentials.resolve(args.key_from)
            saved["detector"] = {"key_from": args.key_from}
            path = credentials.save_config(saved)
            print("Saved to {}. Read the key from {} successfully.".format(path, args.key_from))
            return 0
        key = credentials.resolve(key_from) if key_from else os.environ.get("SAPLING_API_KEY")
        if not key:
            raise credentials.CredentialError(
                "no detector key: run --setup --key-from SOURCE, or set SAPLING_API_KEY")
    except credentials.CredentialError as exc:
        sys.stderr.write("{}\n".format(exc))
        return 2

    if not args.path:
        ap.error("PATH is required")
    if not os.path.isfile(args.path):
        sys.stderr.write("No such file: {}\n".format(args.path))
        return 2
    with open(args.path, encoding="utf-8") as fh:
        text = prose_only(fh.read())

    try:
        result = DETECTORS[args.detector](text, args.timeout, key)
    except urllib.error.HTTPError as exc:
        sys.stderr.write("{} returned HTTP {}\n".format(args.detector, exc.code))
        return 2
    except (urllib.error.URLError, TimeoutError) as exc:
        sys.stderr.write("could not reach {}: {}\n".format(args.detector, exc))
        return 2
    except (KeyError, ValueError) as exc:
        sys.stderr.write("unexpected response from {}: {}\n".format(args.detector, exc))
        return 2

    flagged = sorted(result["sentences"], key=lambda s: -s["score"])[:args.top]
    passed = result["score"] <= args.threshold
    if args.json:
        print(json.dumps({"detector": args.detector, "score": result["score"],
                          "threshold": args.threshold, "passed": passed,
                          "top_sentences": flagged}, indent=2))
    else:
        print("{}: {:.2f} AI probability (threshold {:.2f}). {}".format(
            args.detector, result["score"], args.threshold, "PASS" if passed else "FAIL"))
        if flagged:
            print("\nHighest-scoring sentences, worth a reread:")
            for s in flagged:
                print("  {:.2f}  {}".format(s["score"], s["sentence"][:140]))
        print("\nOne detector's opinion. Use it to find lines to reread, not as the gate.")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
