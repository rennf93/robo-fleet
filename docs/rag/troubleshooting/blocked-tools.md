# Blocked Tools

## There Is No Bash/Shell Tool At All

**Symptom:** You want to run `git commit`, `git push`, `pytest`, `ruff`, or any other shell command, and there is nothing to call.

**Cause:** This is not a permissions restriction (there is no "bash-guard hook" under this runtime) - a delivery agent is a Google ADK `LlmAgent` (`robofleet.agent.adk_entry`) whose only tools are the specific `FunctionTool`s built at spawn from your role's manifest (`robofleet/agent/gateway_shim.py`'s flow/do verbs, plus the seven functions in `robofleet/agent/git_tools.py`). There is no generic shell/Bash tool, no `Write()`/`Edit()`/`Read()` Claude-Code-style tool, and no way to escape to one.

**Solution:** Use the specific tool that matches what you're trying to do - the surface is smaller than a general dev environment, by design:

| You want to | Use instead |
|---|---|
| `git status` | `git_status()` (`robofleet/agent/git_tools.py`) |
| `git log` / `git diff` / `git branch` (list) | **Nothing exists.** No such tool under this runtime; work from `files_changed`/`commits` returned inline by your flow verbs plus `read_file` over actual file content |
| Read/write a file | `read_file(rel_path)` / `write_file(rel_path, content)` |
| Delete/rename a file | `delete_file(rel_path)` / `move_file(src_path, dst_path)` |
| `git commit` + `git push` (devs/docs) | `commit(message, files)` (do-tool) - auto-prefixes `[task_id:8]`, pushes |
| `git checkout` of a task branch | Nothing to call - branch is auto-checked-out by `i_will_work_on(task_id)` (devs) or `i_will_plan(task_id, plan)` (PMs) |
| Open a PR | `open_pr(task_id)` |
| Merge a PR | `complete(task_id, notes)` (PMs only) - Cell PM merges leaf PR; Main PM merges parent and escalates to CEO |
| `git fetch` / `git pull` / `git rebase` | Devs: `sync_branch(task_id)` (fetch + rebase + force-with-lease push). PMs have no rebase verb - escalate a stale integration branch via `escalate_up(...)` |
| `pytest` / `ruff` / `mypy` / `pnpm test` | Nothing to call - you have no local gate. Rely on the project's own CI (runs on your pushed branch after `open_pr`) and QA's review |

## Write Outside Your Worktree

**Symptom:** `write_file`/`delete_file`/`move_file` returns an error (`PermissionError: path traversal outside worktree`)

**Cause:** Every `git_tools.py` function resolves your `rel_path` under `ROBOFLEET_WORKSPACE_DIR` and rejects anything that resolves outside it (`_resolve` in `robofleet/agent/git_tools.py`) - there is no way to read or write outside your own per-task clone. That directory lives under `ROBOFLEET_WORKSPACES_ROOT` (default `/data/workspaces`, or the GCP Filestore NFS mount when armed).

**Solution:** Use a relative path inside your own worktree. QA and other roles without a provisioned workspace get no meaningful write target at all - not because writing is blocked, but because there is no real project clone to write into.

## QA Cannot Commit

**Symptom:** The `commit` do-tool is not in your manifest at all if you are QA

**Cause:** QA's role is read-only by design - `role_config.py`'s `_QA_DO` tuple has no `commit` entry.

**Solution:** QA `pass(task_id, notes, criteria_verified=...)` or `fail(task_id, findings=...)` only. Developers fix issues and re-submit.

## NO_PLAN Error on Start

**Symptom:** Lifecycle transition rejected with NO_PLAN

**Cause:** Parent tasks require a plan before they can leave `pending`.

**Solution:** PMs call `i_will_plan(task_id, plan, approach)`; the verb both records the plan and transitions the task into `in_progress`.

## Parent Branch Required

**Symptom:** Can't claim subtask, error "Parent task must be claimed first"

**Cause:** Parent task hasn't been claimed/started yet, so it has no branch for the subtask's branch to fork from.

**Solution:**

1. Parent task must transition to `in_progress` first (PMs: `i_will_plan(parent_id, plan)`; devs: `i_will_work_on(parent_id)`).
2. Then the subtask's branch will auto-fork from the parent's on claim.

Branches are auto-created hierarchically. No manual creation needed.
