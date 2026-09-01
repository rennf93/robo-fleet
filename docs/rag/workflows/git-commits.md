# Git Commit Workflow

## Commit Format

All commits are automatically prefixed with the task ID by the choreographer:

```
[{task-id-prefix}] {message}
```

Example: `[a1b2c3d4] Add rate limiting endpoint`

You write the message  -  the prefix is added for you. Don't include `[task-id]` yourself; it gets stripped and re-applied.

## Who Can Commit

`commit` is a do-tool (HTTP POST to `/api/v1/do/commit`, `robofleet/agent/gateway_shim.py`  -  no MCP server involved) and is in the manifest only for **developers** and **documenters** (`role_config.py`). PMs delegate code work and call `complete` to merge.

There is **no** `robofleet_git_commit / _push / _create_pr` tool of any kind. The single `commit` do-tool covers commit + push + PR-trigger via the choreographer. The underlying `git_commit`/`git_push` functions in `robofleet/agent/git_tools.py` exist on every role's tool list by construction, but `commit` (the do-tool, with the task-id prefixing + validation + progress-recording) is the sanctioned path.

## Creating Commits

```python
commit(
    message="Add rate limiting endpoint",
    files=["robofleet/api/routes/rate.py"],  # optional; defaults to all staged
)
```

This automatically:

1. Prefixes the commit with `[task-id-first-8-chars]`
2. Validates the message via `commit_validator`
3. Stages the listed files (or everything tracked + modified if omitted)
4. Commits **inside your task worktree** (`{clone_root}/.worktrees/{task-id-first-8}/`)  -  your cwd, never the clone root
5. Pushes the task's recorded branch **by name** (independent of whatever the clone happens to be checked out on)
6. Records the commit on the task (`commits[]` field on `TaskTable`)
7. Opens a PR through the choreographer when the task transitions out of `in_progress` (no separate `create_pr` call required)

## Before Committing

You have no shell tool, so there is no local `pytest`/`ruff`/`mypy`/`pnpm` to run yourself. `read_file` your own change back before committing, and lean on the project's own CI (which runs against your pushed branch after `open_pr`) as the real quality signal. See `docs/rag/roles/developer.md` and `docs/rag/architecture/workspaces.md` for why (this is a hard runtime constraint, not a missing step).

## After Committing

You don't push or create a PR yourself. The choreographer pushed the commit during `commit()`, and the PR is opened/merged as part of the lifecycle transitions:

- `open_pr(task_id)`  -  opens the PR (devs)
- `pass(task_id)` (QA) → `i_documented(task_id)` (doc) → `complete(task_id)` (cell PM merges the leaf PR). Assembled PRs pass the in-path gate first: the cell PM's `submit_up` (cell→root PR) and the main PM's `submit_root` (root→master PR) open the PR and enter `awaiting_pr_review`; after a reviewer `pr_pass`, the cell PM `complete`s to merge cell→root, while the main PM's `complete` escalates the root to the CEO, who merges to master.

## Viewing Commits and History

There is no `git_log`/`git_diff`/branch-listing tool under this runtime. The only worktree-inspection tool is `git_status()` (`robofleet/agent/git_tools.py`, porcelain status text, no branch-tracking info). To see what actually changed, work from `files_changed`/`commits` returned inline by your flow verbs (e.g. `claim_review`'s evidence) plus `read_file` over the real file content.
