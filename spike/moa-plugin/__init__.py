"""SPIKE — auto-MoA as a Hermes plugin. NOT FOR INSTALLATION.

What this file is: the smallest honest skeleton of the plugin that would replace
the 9-file auto-MoA patch. "Honest" means it does not pretend to work: the two
stages that need a seam the framework does not expose are stubs that raise, and a
one-shot probe reports the missing surface at runtime instead of silently doing
nothing.

What lives here and works today (≈21 of 715 patched lines, ≈3%):

    * ``ctx.register_cli_command`` — an ``hermes automoa`` subcommand, wired into
      the CLI at startup with no ``main.py`` change.

What is blocked, and on what (see the spike report for evidence):

    W1  per-generation LLM hook with role tagging — payload must carry ``role``
        ("acting" | "reference" | ...) and the request messages actually sent.
        Without it a plugin sees only the aggregator generation and can neither
        judge nor rewrite advisor output.
    W2  transform hook for the injected context block (counterpart of
        ``transform_tool_result``) — lets a plugin replace the guidance block a
        composite provider attaches to a request.
    W3  variant-selection point before fan-out — lets a plugin pick the preset.
        Without it the auto-router (214 lines) stays in the patch.

Policy note (``plugins/AGENTS.md``): a plugin must not touch core, and a hook with
no concrete consumer is rejected upstream. That is why this skeleton exists as the
consumer to propose W1/W2 alongside — not as a working alternative today.

This directory must NOT be copied into the live tree: ``tools/live_tree_check.py``
allowlists exactly the 9 patch files and treats any other path as NOISE (exit 1).
The real install target would be ``~/.hermes/plugins/hermes-automoa/``.
"""

from __future__ import annotations

import argparse
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

SPIKE_NAME = "hermes-automoa"
SPIKE_REPORT = "docs/superpowers/plans/2026-09-11-moa-plugin-spike.md"

# ── Required surface ─────────────────────────────────────────────────────────
# Each entry: hook/payload field the plugin needs, why, and the patch it blocks.
REQUIRED_SURFACE: dict[str, str] = {
    "role": "W1 — distinguishes the acting generation from advisor sub-generations",
    "advisory_context": "W1 — the material the advisor actually received (the quote corpus)",
    "context_transform": "W2 — right to replace the injected guidance block",
}

_warn_lock = threading.Lock()
_warned_missing: set[str] = set()


def _required_surface_missing(payload: dict[str, Any]) -> list[str]:
    """Which REQUIRED_SURFACE keys this payload lacks (empty = the seam has landed)."""
    return sorted(key for key in REQUIRED_SURFACE if key not in payload)


def _warn_once(missing: list[str]) -> None:
    """One warning per missing field per process — a per-call log would drown the turn."""
    with _warn_lock:
        fresh = [key for key in missing if key not in _warned_missing]
        _warned_missing.update(fresh)
    if fresh:
        detail = "; ".join(f"{key}: {REQUIRED_SURFACE[key]}" for key in fresh)
        logger.warning(
            "%s spike: blocked, missing plugin surface [%s] — advisor stages cannot run. "
            "See %s",
            SPIKE_NAME,
            detail,
            SPIKE_REPORT,
        )


# ── Stages ported from the patch — deliberately unimplemented ────────────────
def _scrub_unverified_tool_claims(text: str, context_text: str) -> tuple[str, int, int]:
    """Stage A of the live patch (~135 lines) — port target: this module, once W1 lands.

    Ported verbatim it would be wrong here: it needs the advisory corpus, which only
    W1 can deliver.
    """
    raise NotImplementedError("blocked on W1 (advisory_context): see " + SPIKE_REPORT)


def _check_verified_quotes(text: str, context_text: str) -> tuple[str, int, int]:
    """Stage B — provenance-contract-as-schema. Design: 2026-09-11-moa-provenance-schema.md."""
    raise NotImplementedError("blocked on W1 (advisory_context): see " + SPIKE_REPORT)


# ── Hooks ────────────────────────────────────────────────────────────────────
def _on_post_llm_call(**payload: Any) -> None:
    """Observe a completed generation. Returns nothing: rewriting needs W2.

    Fires once per turn today, for the acting generation only — so even the
    observation half is incomplete without W1's role tagging.
    """
    missing = _required_surface_missing(payload)
    if missing:
        _warn_once(missing)
        return
    # Seam landed. Neither stage may run unguarded, though: fail-open, like the patch.
    try:
        _scrub_unverified_tool_claims(str(payload.get("text") or ""), str(payload["advisory_context"]))
        _check_verified_quotes(str(payload.get("text") or ""), str(payload["advisory_context"]))
    except Exception as exc:  # never break a turn
        logger.warning("%s spike stage failed (fail-open): %s", SPIKE_NAME, exc, exc_info=True)


def _on_pre_llm_call(**payload: Any) -> None:
    """Injection point for the plugin's own context, once per turn, before the tool loop.

    Kept registered to show the boundary: this hook reaches the *user message* of the
    turn, not the advisor system prompt and not the MoA guidance block (W2).
    """
    _ = payload


# ── CLI — the one slice that works today ─────────────────────────────────────
def _setup_cli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the spike status as JSON (for scripts).",
    )


def _cmd_status(args: argparse.Namespace) -> int:
    """``hermes automoa --status`` — report which surfaces are still missing."""
    missing = sorted(REQUIRED_SURFACE)
    payload: dict[str, Any] = {
        "plugin": SPIKE_NAME,
        "stage": "spike",
        "installable": False,
        "missing_surface": {key: REQUIRED_SURFACE[key] for key in missing},
        "report": SPIKE_REPORT,
    }
    if getattr(args, "json", False):
        import json

        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"{SPIKE_NAME} — spike, not installable.")
    print("Blocked on generic hook widenings:")
    for key in missing:
        print(f"  - {key}: {REQUIRED_SURFACE[key]}")
    print(f"Evidence and verdict: {SPIKE_REPORT}")
    return 0


def register(ctx) -> None:
    """Plugin entry point (``plugins/<name>/__init__.py`` -> ``register(ctx)``)."""
    ctx.register_hook("post_llm_call", _on_post_llm_call)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_cli_command(
        "automoa",
        "Report the auto-MoA plugin spike status (not an installable plugin).",
        _setup_cli,
        _cmd_status,
        description="SPIKE: surfaces still missing before auto-MoA can leave the 9-file patch.",
    )
    logger.debug("%s registered (spike): hooks + CLI", SPIKE_NAME)
