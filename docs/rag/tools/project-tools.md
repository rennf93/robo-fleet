# Project & Workspace Tools

## Overview

There is **no** `robofleet_project_*` or `robofleet_workspace_*` agent tool. Agents do **not** create projects, manage git tokens, or ensure workspaces. Those are handled for you:

- **Workspaces are auto-cloned by the orchestrator** (`WorkspaceService`). Your per-agent clone of the project repo is created the first time you claim work on it  -  you never call a workspace tool. Branches are auto-created on `i_will_work_on()` / `claim_review()`; you don't run `git checkout` either.
- **Project registration and git-token management are operator actions** done through the control panel / HTTP API, not from inside an agent container. Tokens are encrypted at rest; the agent container never sees the PAT (it is injected into git operations server-side and scrubbed from URLs).

## What a task already tells you

A task carries its project linkage; you don't look it up with a tool. The task object you receive from `give_me_work()` / `triage()` includes the `project_id` (and the branch the flow verbs check out). Acceptance criteria and the project context come back inline on the Envelope.

## Inspecting the repo

There is no MCP server here  -  the only worktree-inspection tool is `git_status()` (`robofleet/agent/git_tools.py`, an ADK `FunctionTool`, HTTP-free, running in your own container). There is no `git_log`, `git_diff`, or branch-listing tool of any kind under this runtime; use `read_file` over the checked-out worktree plus the `files_changed`/`commits` data your flow verbs already return inline.

There is **no** `robofleet_git_commit / _push / _checkout / _create_pr / _merge_pr` tool either. Commits go through the `commit` do-tool (auto-prefixed with `[task_id:8]`, auto-pushed by the choreographer); PRs open at `open_pr` time; merges are a PM `complete` operation. `git_commit`/`git_push` in `git_tools.py` are the real underlying functions, present on every role's tool list by construction but not the sanctioned commit path for anyone but developer/documenter.

## Finding project knowledge

There is **no KB-search tool reachable from this runtime.** `robofleet_kb_search`/`robofleet_ask_mentor` exist in the codebase but are wired only for the legacy Docker/CLI-container provider path, never for `ADK_CLOUD_RUN` (see `docs/rag/README.md`). To understand a project's layout, `read_file` the files you need directly, or rely on whatever the task prompt/evidence already handed you.

## PM note: creating work

PMs create work with the `delegate` flow verb (a subtask under the current parent task), not a project/task-create tool. `delegate` takes an optional `project_id`; the parent task's project is inherited when you omit it. There is no agent-facing standalone project- or task-create tool.
