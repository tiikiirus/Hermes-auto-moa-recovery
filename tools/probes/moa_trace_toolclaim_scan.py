"""Read-only scan of a MoA trace for tool-echo lines in advisor outputs.

Usage:
    python tools/probes/moa_trace_toolclaim_scan.py [path/to/trace.jsonl]

For every record it walks ``references[].output`` and counts lines that start
with the tool-echo markers the anti-fabrication scrubber targets
(``[called tool:`` / ``[tool result:``), grouped by advisor model family, and
reports whether the aggregator guidance header carrying the
unverified-advisor note is present. Writes nothing.
"""
from __future__ import annotations

import collections
import json
import sys

FAMILIES = ("inclusionai", "poolside", "meituan", "stepfun")
STRICT_PREFIXES = ("[called tool:", "[tool result:")
LOOSE_PREFIXES = ("[called tool:", "[tool result:")
GUIDANCE_NEEDLES = ("непроверенные мнения", "unverified advisor opinions")

DEFAULT_TRACE = (
    r"C:/Users/tiki/AppData/Local/hermes/profiles/fantrax/moa-traces/"
    r"20260909_212807_4478b2.jsonl"
)


def family_of(model: str | None) -> str:
    low = (model or "").lower()
    for fam in FAMILIES:
        if fam in low:
            return fam
    return low.split("/", 1)[0] or "unknown"


def main(path: str) -> int:
    total_refs = 0
    records = 0
    skipped = 0
    strict: collections.Counter[str] = collections.Counter()
    loose: collections.Counter[str] = collections.Counter()
    model_counts: collections.Counter[str] = collections.Counter()
    output_lines: collections.Counter[str] = collections.Counter()
    guidance_records = 0
    examples: list[str] = []

    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except Exception:
                skipped += 1
                continue
            records += 1
            blob_parts: list[str] = []
            for ref in rec.get("references") or []:
                total_refs += 1
                model = ref.get("model")
                fam = family_of(model)
                model_counts[f"{fam}: {model}"] += 1
                out = ref.get("output")
                if not isinstance(out, str):
                    continue
                blob_parts.append(out)
                for line in out.splitlines():
                    output_lines[fam] += 1
                    stripped = line.strip()
                    if stripped.startswith(STRICT_PREFIXES):
                        strict[fam] += 1
                        if len(examples) < 8:
                            examples.append(f"[{fam}] {stripped[:140]}")
                    if stripped.lower().startswith(LOOSE_PREFIXES):
                        loose[fam] += 1
            for msg in (rec.get("aggregator") or {}).get("input_messages") or []:
                content = msg.get("content")
                if isinstance(content, str):
                    blob_parts.append(content)
            blob = "\n".join(blob_parts)
            if any(needle in blob for needle in GUIDANCE_NEEDLES):
                guidance_records += 1

    print(f"trace                : {path}")
    print(f"records              : {records} (unparsed: {skipped})")
    print(f"total_references     : {total_refs}")
    print(f"advisor_output_lines : {sum(output_lines.values())}")
    print("reference counts by model:")
    for key, count in model_counts.most_common():
        print(f"  {key}: {count}")
    print("tool_like_lines (strict startswith, per family):")
    for fam in FAMILIES:
        print(f"  {fam}: {strict.get(fam, 0)}")
    print(f"  TOTAL strict: {sum(strict.values())}")
    print("tool_like_lines (case-insensitive startswith):")
    for fam in FAMILIES:
        print(f"  {fam}: {loose.get(fam, 0)}")
    print(f"  TOTAL loose: {sum(loose.values())}")
    print(f"guidance_records_with_note: {guidance_records}/{records}")
    for ex in examples:
        print(f"  example: {ex}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TRACE))
