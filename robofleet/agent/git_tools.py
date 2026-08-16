"""ADK FunctionTools wrapping git + file ops inside the agent worktree.

Each tool operates on ``ROBOFLEET_WORKSPACE_DIR`` (the per-agent clone). File ops
resolve the relative path and reject any path that escapes the worktree root
(``..`` traversal). Git ops run ``git -C <worktree> ...`` via subprocess. Push
uses the ``x-access-token:<token>`` extraheader against ``ROBOFLEET_GIT_TOKEN``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from google.adk.tools import FunctionTool


def _worktree() -> Path:
    # ROBOFLEET_WORKSPACE_DIR is the explicit form (set by the Cloud Run provider
    # and the docker -w path). When unset, fall back to the process cwd: both
    # deploy targets arrange cwd == workspace (-w / working_dir), so the tools
    # resolve correctly without a hard KeyError on every git/file call.
    env_dir = os.environ.get("ROBOFLEET_WORKSPACE_DIR")
    return (Path(env_dir) if env_dir else Path.cwd()).resolve()


def _resolve(rel: str) -> Path:
    """Resolve ``rel`` under the worktree, rejecting traversal outside it."""
    root = _worktree()
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise PermissionError(f"path traversal outside worktree: {rel}") from None
    return target


def _ok(**fields: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"status": "ok"}
    d.update(fields)
    return d


def _err(message: str) -> dict[str, Any]:
    return {"status": "error", "message": message}


def _git(args: list[str], token: str | None = None) -> subprocess.CompletedProcess[str]:
    wt = _worktree()
    cmd: list[str] = ["git", "-C", str(wt)]
    if token:
        cmd += ["-c", f"http.extraheader=Authorization: Basic x-access-token:{token}"]
    return subprocess.run([*cmd, *args], capture_output=True, text=True, check=False)


async def read_file(rel_path: str) -> dict[str, Any]:
    """Read a file inside the worktree, returning its text content."""
    try:
        target = _resolve(rel_path)
    except PermissionError as exc:
        return _err(str(exc))
    if not target.exists():
        return _err(f"not found: {rel_path}")
    return _ok(content=target.read_text())


async def write_file(rel_path: str, content: str) -> dict[str, Any]:
    """Write text content to a file inside the worktree."""
    try:
        target = _resolve(rel_path)
    except PermissionError as exc:
        return _err(str(exc))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return _ok(path=str(rel_path))


async def git_commit(message: str) -> dict[str, Any]:
    """Stage all changes and commit with ``message``."""
    _git(["add", "-A"])
    res = _git(["commit", "-m", message])
    if res.returncode != 0:
        return _err(res.stderr.strip() or res.stdout.strip())
    sha_res = _git(["rev-parse", "HEAD"])
    return _ok(sha=sha_res.stdout.strip())


async def git_status() -> dict[str, Any]:
    """Return the porcelain status of the worktree."""
    res = _git(["status", "--porcelain"])
    return _ok(status_text=res.stdout)


async def git_push(remote: str = "origin", branch: str = "HEAD") -> dict[str, Any]:
    """Push ``branch`` to ``remote`` using the x-access-token extraheader."""
    token = os.environ.get("ROBOFLEET_GIT_TOKEN", "")
    if not token:
        return _err("ROBOFLEET_GIT_TOKEN not set; cannot push")
    res = _git(["push", remote, branch], token=token)
    if res.returncode != 0:
        return _err(res.stderr.strip() or res.stdout.strip())
    return _ok(remote=remote, branch=branch)


def _wrap(fn: Any, name: str) -> FunctionTool:
    fn.__name__ = name
    return FunctionTool(fn)


def build_git_tools() -> list[FunctionTool]:
    """Build the ADK FunctionTools for file + git ops over the worktree."""
    return [
        _wrap(read_file, "read_file"),
        _wrap(write_file, "write_file"),
        _wrap(git_commit, "git_commit"),
        _wrap(git_status, "git_status"),
        _wrap(git_push, "git_push"),
    ]
