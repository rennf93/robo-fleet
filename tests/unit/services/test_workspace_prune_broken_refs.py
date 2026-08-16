"""`WorkspaceService._prune_broken_refs` drops debris loose refs before a fetch.

Interrupted hard-stop recovery can leave `.bak` ref debris and truncated/garbage
loose-ref files under `.git/refs`. The prune reads files only (no git subprocess),
so these tests just stage a `.git/refs` tree on disk.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from roboco.services.workspace import WorkspaceService

if TYPE_CHECKING:
    from pathlib import Path

_VALID_SHA1 = "a" * 40
_VALID_SHA256 = "b" * 64


def _make_heads(workspace: Path) -> Path:
    heads = workspace / ".git" / "refs" / "heads"
    heads.mkdir(parents=True)
    return heads


def test_keeps_valid_sha1_ref(tmp_path: Path) -> None:
    good = _make_heads(tmp_path) / "main"
    good.write_text(_VALID_SHA1 + "\n", encoding="utf-8")
    WorkspaceService._prune_broken_refs(tmp_path)
    assert good.exists()


def test_keeps_valid_sha256_ref(tmp_path: Path) -> None:
    good = _make_heads(tmp_path) / "main"
    good.write_text(_VALID_SHA256 + "\n", encoding="utf-8")
    WorkspaceService._prune_broken_refs(tmp_path)
    assert good.exists()


def test_keeps_symref(tmp_path: Path) -> None:
    sym = _make_heads(tmp_path) / "current"
    sym.write_text("ref: refs/heads/main\n", encoding="utf-8")
    WorkspaceService._prune_broken_refs(tmp_path)
    assert sym.exists()


def test_removes_bak_debris_even_with_valid_content(tmp_path: Path) -> None:
    bak = _make_heads(tmp_path) / "feature.bak"
    bak.write_text(_VALID_SHA1, encoding="utf-8")
    WorkspaceService._prune_broken_refs(tmp_path)
    assert not bak.exists()


def test_removes_garbage_ref(tmp_path: Path) -> None:
    junk = _make_heads(tmp_path) / "broken"
    junk.write_text("not-a-sha-or-symref garbage", encoding="utf-8")
    WorkspaceService._prune_broken_refs(tmp_path)
    assert not junk.exists()


def test_no_git_refs_dir_is_noop(tmp_path: Path) -> None:
    # No .git/refs present — must not raise.
    WorkspaceService._prune_broken_refs(tmp_path)
