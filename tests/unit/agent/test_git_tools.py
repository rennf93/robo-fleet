"""Tests for robofleet.agent.git_tools: git + file FunctionTools over the worktree."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from google.adk.tools import FunctionTool


@pytest.fixture
def worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temp git worktree the tools operate on, set as ROBOFLEET_WORKSPACE_DIR."""
    # Neutralize the operator's global core.hooksPath (identity hook) so the
    # test commits with the synthetic Test identity below succeed.
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/dev/null")
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", str(origin)], check=True, capture_output=True
    )
    wt = tmp_path / "wt"
    subprocess.run(
        ["git", "clone", str(origin), str(wt)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(wt), "config", "user.email", "t@t.test"], check=True
    )
    subprocess.run(["git", "-C", str(wt), "config", "user.name", "Test"], check=True)
    monkeypatch.setenv("ROBOFLEET_WORKSPACE_DIR", str(wt))
    return wt


@pytest.mark.asyncio
async def test_read_file_round_trip(worktree: Path) -> None:
    from robofleet.agent.git_tools import read_file, write_file

    res = await write_file("sub/notes.txt", "hello world")
    assert res["status"] == "ok"
    data = await read_file("sub/notes.txt")
    assert data["status"] == "ok"
    assert data["content"] == "hello world"


@pytest.mark.asyncio
async def test_read_file_rejects_traversal(worktree: Path) -> None:
    from robofleet.agent.git_tools import read_file

    (worktree.parent / "secret.txt").write_text("secret")
    res = await read_file("../secret.txt")
    assert res["status"] == "error"
    assert "traversal" in res["message"].lower() or "outside" in res["message"].lower()


@pytest.mark.asyncio
async def test_write_file_rejects_traversal(worktree: Path) -> None:
    from robofleet.agent.git_tools import write_file

    res = await write_file("../escaped.txt", "x")
    assert res["status"] == "error"


@pytest.mark.asyncio
async def test_git_commit_creates_commit(worktree: Path) -> None:
    from robofleet.agent.git_tools import git_commit, write_file

    await write_file("a.txt", "a")
    res = await git_commit("first commit")
    assert res["status"] == "ok"
    log = subprocess.run(
        ["git", "-C", str(worktree), "log", "--oneline"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "first commit" in log


@pytest.mark.asyncio
async def test_git_status_returns_porcelain(worktree: Path) -> None:
    from robofleet.agent.git_tools import git_status, write_file

    await write_file("uncommitted.txt", "u")
    res = await git_status()
    assert res["status"] == "ok"
    assert "uncommitted.txt" in res["status_text"]


def test_build_git_tools_returns_functiontools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ROBOFLEET_WORKSPACE_DIR", str(tmp_path))
    from robofleet.agent.git_tools import build_git_tools

    tools = build_git_tools()
    assert len(tools) >= 5
    assert all(isinstance(t, FunctionTool) for t in tools)
    # git_push is present even if not exercised against a real origin here
    names = {getattr(t, "name", None) for t in tools}
    assert any("push" in str(n) for n in names if n)


@pytest.mark.asyncio
async def test_git_push_missing_token_errors_clean(
    worktree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """git_push without a token returns an error envelope, does not hang."""
    monkeypatch.delenv("ROBOFLEET_GIT_TOKEN", raising=False)
    from robofleet.agent.git_tools import git_push

    res = await git_push(remote="origin", branch="HEAD")
    assert res["status"] == "error"


def test_worktree_falls_back_to_cwd_when_env_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_worktree() falls back to the process cwd when ROBOFLEET_WORKSPACE_DIR is
    unset. This is the root-cause fix for the latent 3.2 bug: every ADK git/file
    tool KeyErrored before this fallback because no production path sets the
    env var (docker only sets cwd via -w, Cloud Run sets working_dir)."""
    monkeypatch.delenv("ROBOFLEET_WORKSPACE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    from robofleet.agent.git_tools import _worktree

    assert _worktree() == tmp_path.resolve()


@pytest.mark.asyncio
async def test_read_file_works_via_cwd_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """read_file resolves against the cwd fallback when the env var is unset,
    proving the fallback makes the file tools functional without the env var."""
    monkeypatch.delenv("ROBOFLEET_WORKSPACE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("hello via cwd")
    from robofleet.agent.git_tools import read_file

    res = await read_file("notes.txt")
    assert res["status"] == "ok"
    assert res["content"] == "hello via cwd"


def test_worktree_env_var_wins_over_cwd_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ROBOFLEET_WORKSPACE_DIR IS set, it takes precedence over cwd (the
    existing setenv path stays unchanged)."""
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    monkeypatch.setenv("ROBOFLEET_WORKSPACE_DIR", str(explicit))
    monkeypatch.chdir(tmp_path)
    from robofleet.agent.git_tools import _worktree

    assert _worktree() == explicit.resolve()
