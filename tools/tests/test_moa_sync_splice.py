"""Regression: ``moa_sync.py --sync`` must not destroy config comments.

The old writer re-serialized the WHOLE ``config.yaml`` through PyYAML, which
silently drops every comment a human wrote. ``profiles/aiqa``, ``profiles/fantrax``
and ``profiles/local-llm-lab`` carry 36 comment lines each (they document the MoA
rationale), so a sync was a documentation-eating operation.

The writer now splices only the top-level ``moa:`` block. This test pins that
contract, including the one documented casualty: comments *inside* the ``moa:``
block are lost, because that region is the part being replaced.

Run:  <hermes venv>/python.exe -m pytest tools/tests -q
"""
from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

TOOLS_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))

import moa_sync  # noqa: E402

PRESET_NAMES = (
    "default", "code_logic_deep", "logic_deep", "code_visual_deep", "logic_visual_deep",
    "free_auto_moa", "pay_default", "pay_code_logic_deep", "pay_logic_deep",
    "pay_code_visual_deep", "pay_logic_visual_deep", "pay_auto_moa",
)
PAY_PRESETS = frozenset(name for name in PRESET_NAMES if name.startswith("pay_"))

OUTSIDE_COMMENT = "# model section: kept by hand, must survive a sync\n"
INSIDE_COMMENT = "  # comment inside the moa block\n"


def _presets() -> dict[str, dict]:
    """A minimal graph that passes ``semantic_checks`` (12 presets, pay aggregators)."""
    out: dict[str, dict] = {}
    for name in PRESET_NAMES:
        aggregator = "z-ai/glm-5.3-flash" if name in PAY_PRESETS else "meituan/longcat-2.0:free"
        out[name] = {
            "reference_models": [{"provider": "nous", "model": "inclusionai/ling-3.0-flash-fin:free"}],
            "aggregator": {"provider": "nous", "model": aggregator},
            "reference_max_tokens": 2048,
        }
    return out


def _canonical_moa() -> dict:
    return {
        "presets": _presets(),
        "save_traces": True,
        "privacy_filter": "full",
        "default_preset": "default",
    }


def _write_drifted_profile(path: pathlib.Path) -> None:
    """A profile whose moa block has drifted, wrapped in comments that must live."""
    path.write_text(
        OUTSIDE_COMMENT
        + "model:\n"
        + "  provider: moa\n"
        + "  default: free_auto_moa\n"
        + "moa:\n"
        + "  default_preset: free_auto_moa\n"
        + INSIDE_COMMENT
        + "  presets:\n"
        + "    default:\n"
        + "      reference_max_tokens: 1\n"
        + "skills:\n"
        + "  kept: true\n",
        encoding="utf-8",
    )


@pytest.fixture()
def sync_env(tmp_path, monkeypatch):
    """A throwaway repo + profile, with moa_sync's module paths redirected."""
    repo = tmp_path / "recovery"
    repo.mkdir()
    (repo / "auto-moa-moa-section.yaml").write_text(
        yaml.safe_dump({"moa": _canonical_moa()}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    profile = tmp_path / "config.yaml"
    _write_drifted_profile(profile)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(moa_sync, "PROFILE_PATHS", {"default": profile})
    monkeypatch.setattr(moa_sync, "EXPECTED_DEFAULTS", {"default": "free_auto_moa"})
    return repo, profile


def _sync(profile: pathlib.Path) -> None:
    """Run --sync and, on failure, show the resulting file (the whole point is its state)."""
    rc = moa_sync.main()
    assert rc == 0, (
        "moa_sync --sync failed (rc=%d). File after the attempt:\n%s"
        % (rc, profile.read_text(encoding="utf-8"))
    )


def test_splice_replaces_only_the_moa_block():
    original = OUTSIDE_COMMENT + "model:\n  provider: moa\nmoa:\n  default_preset: x\nskills:\n  kept: true\n"
    spliced = moa_sync.splice_moa_block(original, {"presets": {}, "default_preset": "y"})

    head, _, tail = spliced.partition("moa:\n")
    assert head == OUTSIDE_COMMENT + "model:\n  provider: moa\n"
    assert "default_preset: y" in tail
    assert tail.endswith("skills:\n  kept: true\n"), "everything after the block must be untouched"
    assert yaml.safe_load(spliced)["model"] == {"provider": "moa"}


def test_column_zero_comment_does_not_end_the_block():
    """A '#' line can never open a top-level block, even at column 0.

    Treating one as the boundary leaves the tail of the old ``moa:`` block in the
    file (the new block is inserted, the remainder is not removed), which is how
    a fixture put two moa blocks in one document.
    """
    original = "moa:\n  a: 1\n# stray comment at column zero\n  b: 2\nskills:\n  kept: true\n"
    spliced = moa_sync.splice_moa_block(original, {"presets": {"p": {}}, "x": 1})

    parsed = yaml.safe_load(spliced)
    assert parsed["skills"] == {"kept": True}, "the block after moa: must survive"
    assert parsed["moa"] == {"presets": {"p": {}}, "x": 1}
    assert spliced.count("moa:") == 1, "the old block must be fully removed"
    assert "  a: 1" not in spliced


def test_splice_raises_when_there_is_no_moa_block():
    with pytest.raises(ValueError, match="no top-level 'moa:' block"):
        moa_sync.splice_moa_block("model:\n  provider: moa\n", {"presets": {}})


def test_sync_preserves_comments_outside_the_moa_block(sync_env, monkeypatch):
    repo, profile = sync_env
    monkeypatch.setattr(sys, "argv", ["moa_sync.py", "--sync", "--repo", str(repo)])

    _sync(profile)

    text = profile.read_text(encoding="utf-8")
    assert OUTSIDE_COMMENT in text, "comment outside the moa block was destroyed"
    assert yaml.safe_load(text)["skills"] == {"kept": True}
    assert len(yaml.safe_load(text)["moa"]["presets"]) == 12, "the moa graph should now be canonical"
    assert moa_sync.needs_sync(yaml.safe_load(text), moa_sync.merged_moa(
        yaml.safe_load(text), _canonical_moa(), "default")) is False


def test_comment_inside_the_moa_block_is_the_documented_casualty(sync_env, monkeypatch):
    repo, profile = sync_env
    monkeypatch.setattr(sys, "argv", ["moa_sync.py", "--sync", "--repo", str(repo)])

    _sync(profile)
    assert INSIDE_COMMENT not in profile.read_text(encoding="utf-8")


def test_sync_is_idempotent(sync_env, monkeypatch):
    repo, profile = sync_env
    monkeypatch.setattr(sys, "argv", ["moa_sync.py", "--sync", "--repo", str(repo)])
    _sync(profile)
    after_first = profile.read_bytes()

    assert moa_sync.main() == 0
    assert profile.read_bytes() == after_first, "a second sync must be a byte-identical no-op"


def test_check_reports_pass_without_writing(sync_env, monkeypatch):
    repo, profile = sync_env
    before = profile.read_bytes()
    monkeypatch.setattr(sys, "argv", ["moa_sync.py", "--check", "--repo", str(repo)])

    assert moa_sync.main() == 1, "a drifted profile must fail --check"
    assert profile.read_bytes() == before, "--check must never write"
