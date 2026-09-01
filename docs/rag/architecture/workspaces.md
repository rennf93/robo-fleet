# Workspace Structure

## Multi-Agent Isolation

Each agent gets their own git clone:

```
{workspaces_root}/
└── {project-slug}/
    └── {team}/
        └── {agent-slug}/
            └── [git repo files]
```

## Example

```
/data/workspaces/
└── robofleet/
    ├── backend/
    │   ├── be-dev-1/    # be-dev-1's workspace
    │   ├── be-dev-2/    # be-dev-2's workspace
    │   ├── be-qa/       # be-qa's workspace
    │   ├── be-pm/       # be-pm's workspace
    │   └── be-doc/      # be-doc's workspace
    ├── frontend/
    │   ├── fe-dev-1/
    │   └── ...
    └── ux_ui/
        └── ...
```

## Configuration

```bash
# Environment variables
ROBOFLEET_WORKSPACES_ROOT=/data/workspaces
ROBOFLEET_WORKSPACE_AUTO_CLONE=true
ROBOFLEET_WORKSPACE_CLONE_TIMEOUT=300
```

## Features

| Feature | Description |
|---------|-------------|
| Auto-clone | Workspaces created on first access |
| Isolation | No file locking conflicts |
| Branch independence | Agents on different branches |
| Project-scoped | Organized by project slug |

## Benefits

1. **Parallel Development**: Multiple agents on same project
2. **No Conflicts**: Each has own working tree
3. **Branch Flexibility**: Different branches simultaneously
4. **Clean State**: Fresh clone if needed

## Per-Task Worktrees (F123)

Your agent clone is **shared across all your tasks**, but each **claimed task** gets its own linked git worktree  -  a separate working directory on the same underlying clone  -  so two of your in-progress tasks never clobber each other on one checkout (this is what lets a coordinator PM hold several roots at once, and what stops a fresh claim from `reset --hard`-ing uncommitted work on your still-active first task).

```
{workspaces_root}/{project}/{team}/{agent}/        # the clone root (shared)
├── .git/                  # the real object store (shared)
├── .venv/                 # the per-project venv (shared, agent-owned)
├── .uv-python/            # uv's managed CPython (shared, gitignored)
└── .worktrees/
    └── {task-short}/      # ONE per claimed task  -  your cwd for that task
        ├── .venv -> ../../.venv   # symlink to the clone-root venv
        └── [your task's checked-out branch]
```

- **Claim** (`i_will_work_on` / `claim_review` / `claim_doc_task`) adds a worktree at `.worktrees/{task-id-first-8}/` and checks out the task's branch there. The clone root's HEAD is **never moved** by a claim.
- **Your container/Job is started with its working directory (and `ROBOFLEET_WORKSPACE_DIR`) pointing at the worktree** for your current task, so `git_tools.py`'s `read_file`/`write_file`/`git_commit`/etc. all resolve there automatically. Spawn resolves the worktree from your `current_task_id` on every spawn (never cached), so a resume/respawn re-attaches a pruned worktree before launch. Every spawn also RE-SYNCS an already-present worktree against origin (role-aware): if you're a developer/documenter, your own dirty uncommitted edits are never discarded to do it  -  a behind-or-equal worktree fast-forwards, a strictly-ahead one (your own unpushed commits) is left exactly alone; if you're QA/PR-gate/PM reviewing someone else's branch, a diverged worktree hard-resets to origin, since your local history there can only ever be a stale prior-round checkout. This closes the "reviewer keeps re-examining its own frozen round-1 checkout across a multi-round bounce" class  -  you're never respawned onto commits older than what's actually on the branch.
- **The clone-root `.venv` is shared**  -  each worktree's `.venv` is a symlink to `../../.venv`. This matters only for the legacy Docker/CLI-container providers, which run `uv` themselves; an ADK delivery agent has no shell tool and never invokes it.
- **Git ops split by kind**: checkout/HEAD-moving ops (`create_branch`, `commit`, `rebase`, `checkout`) target the worktree; branch-by-name ops (`push`, `pull`, `fetch`, `pr_merge`, `diff`) run from the clone root. You never do either by hand  -  the verbs resolve the worktree for you.
- **One active WorkSession per task** is enforced both in the service layer and by a DB unique index  -  a re-claim (pool release, reaper unclaim, escalation redirect) supersedes any prior agent's stale session for that task.
- **Claim rollback** (a mid-claim failure) `worktree remove --force`s the worktree so a retry doesn't collide with a stale one.
- **Terminal completion** (`complete` / `ceo_approve`) and **cancellation** remove the assignee's worktree AND force-delete the now-spent local branch ref in the clone, so finished/cancelled tasks don't leak either on disk. A `needs_revision` bounce keeps both  -  you need the branch back. The stale-claim reaper does **not** remove the worktree or branch; it routes the task to `pending` for a re-claim that reuses them. A PM/CEO can also run a backlog stale-branch sweep from the panel's Git page for older completed/cancelled tasks whose ref survived from before this reaping existed.

You do not manage any of this. The verbs do. The only thing you must know: **`read_file`/`write_file`/etc. resolve relative to the worktree for your current task, not the clone root**.

## `uv run --active` / `/app/.venv` corruption  -  legacy providers only, not you

This entire class of incident does not apply to a delivery agent under the ADK runtime: you have no shell/Bash tool, so you cannot run `uv run`, `uv run --active`, or anything else against `/app/.venv` in the first place. `robofleet.agent.adk_entry`'s container ships a single image-baked venv for the ADK Python runtime itself (`google-adk`, `google-genai`, the gateway shim) - there is no separate "MCP-gateway venv" concept here, because there are no MCP servers.

The predecessor incident this section used to describe - an agent following uv's `--active` hint and bricking a shared image-baked venv fleet-wide - was specific to the legacy Docker/CLI-container provider path (Grok/Codex/Gemini-CLI/Kimi, plus the interactive Intake/Secretary containers), which DOES give its agent a real shell tool and DOES carry a bash-guard hook that blocks `uv run --active` / any `uv run`/`uvx` targeting `/app`. If you are working on that code path, the same hazard and guard still apply there; a delivery agent reading this file does not need to think about it.

## No Workspace Tools  -  It's Automatic

There are **no** agent-facing workspace tools. Workspaces and per-task worktrees are created for you by the orchestrator (`WorkspaceService`) before your container starts. You never `ensure`, `clone`, `checkout`, or `worktree add` by hand  -  your repo is already on disk, the worktree for your current task is already linked and `-w`'d as your cwd, and the gateway verbs (`i_will_work_on`, `claim_review`, ...) check out the right branch in it.

## Workspace Resolution

Path resolved automatically: `{workspaces_root}/{project}/{team}/{agent}/`

If `auto_clone=True` and workspace doesn't exist, it's created on first access.

## Authentication

HTTPS repositories require a git token configured on the project  -  the field is historically named for GitHub PATs but works unchanged for a project registered against Gitea or GitLab (`projects.git_provider`):

- **Token configured**: Auto-clone works, git operations succeed
- **Token missing**: Error "Project requires a git token for HTTPS repositories"

**If you see this error**: Contact your PM. The project's git token is configured by a human in the control panel (project settings)  -  it is not an agent tool. The token is encrypted at rest and never exposed to your container; the orchestrator injects it into git operations for you.
