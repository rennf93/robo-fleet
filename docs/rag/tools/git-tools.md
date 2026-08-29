# Git Tools

There is **no** MCP server here at all, and no `robofleet_git_commit / _push / _create_pr / _merge_pr / _checkout` tool. Your git surface is exactly two things: the seven ADK `FunctionTool`s in `robofleet/agent/git_tools.py` (operating on your own worktree, `ROBOFLEET_WORKSPACE_DIR`), and the gateway verbs (`commit`, `open_pr`, `complete`, `submit_up`, `submit_root`) that drive git as a side effect through the orchestrator.

## Worktree operations  -  `robofleet/agent/git_tools.py`

Every role's manifest carries these by construction (`robofleet.agent.adk_entry`'s `main()` calls `build_git_tools()` unconditionally for every role, not just developers)  -  whether they resolve to anything useful depends on whether your role has a provisioned workspace.

| Tool | Purpose |
|------|---------|
| `read_file(rel_path)` | Read a file's text content |
| `write_file(rel_path, content)` | Write a file |
| `delete_file(rel_path)` | Delete a file |
| `move_file(src_path, dst_path)` | Rename/move a file |
| `git_commit(message)` | `git add -A && git commit -m message` in your worktree, returns the sha |
| `git_status()` | Porcelain status text |
| `git_push(remote="origin", branch="HEAD")` | Push using the `x-access-token` extraheader against `ROBOFLEET_GIT_TOKEN` |

**There is no `git_log`, `git_diff`, or branch-listing tool of any kind.** If you need to know what changed, work from `files_changed`/`commits` returned inline by your flow verbs (e.g. `claim_review`'s evidence) plus `read_file` over the actual file content  -  not a diff. A path outside your worktree is rejected (`PermissionError`, "path traversal outside worktree") by every one of these functions; there is no way to read or write outside your own clone.

`git_commit`/`git_push` are real functions, not raw shell  -  you have no generic Bash/shell tool at all, so "native git is blocked" isn't a hook restriction here, it's simply that no such tool exists to call.

## Branch Lifecycle  -  automatic

Branches are auto-created when an agent transitions a task to `in_progress`. Real format (`robofleet/templates/git/branch.py`, `build_branch_name`): each `*_short` is the task UUID's first 8 characters, `--` separates hierarchy levels, max 4 levels deep (MegaTask's umbrella layer is the 4th):

- Root task -> `feature/team/ROOT_SHORT`
- Subtask -> `feature/team/ROOT_SHORT--SUB_SHORT`
- Sub-subtask -> `feature/team/ROOT_SHORT--SUB_SHORT--SUBSUB_SHORT`

You never run `git checkout` or `git branch` yourself; calling `i_will_work_on(task_id)` (developers) or `i_will_plan(task_id, plan)` (PMs) creates the branch and switches your workspace to it.

## Write Path  -  by role

### Developers and Documenters -> `commit` (do-tool)

```python
# Commit on your active task's branch. The gateway's commit() action:
#  - prefixes the message with [task_id:8]
#  - validates the subject via commit_validator (>=20 chars, not a banned
#    single word: wip/tmp/asdf/oops/fix/update/change/stuff/things)
#  - pushes to the remote branch
#  - opens a PR when the task transitions out of in_progress (open_pr)
commit(message="Add rate limiting endpoint", files=["robofleet/api/routes/rate.py"])
```

There is no separate `push` step and no separate `create_pr` step. Both are side-effects of the lifecycle transitions the verbs already drive. Conventional-Commits shape (`type(scope): subject`) is a soft hint on mismatch, not a hard requirement.

On a project that checks in generated artifacts, the push step also regenerates them: right before your branch is pushed, the project's codegen command runs, and any drift it produces is committed into the SAME push automatically.

### PMs -> `complete` (flow verb)

```python
# Cell PM completing a leaf task: merges the leaf PR.
# (Assembled cell->root / root->master PRs are opened by submit_up / submit_root
#  and gated in awaiting_pr_review first.) After a code root's gate clears,
# the Main PM's complete escalates to the CEO  -  the CEO merges root->master.
complete(task_id="a1b2c3d4-...", notes="QA passed; docs complete; ready to ship.")
```

PMs never run `git` directly and don't call the `commit` do-tool (not in their manifest). PMs `delegate` code work to devs, then `complete` to merge once QA + docs sign off.

## Branch Naming Convention

`{type}/{team}/{task-hierarchy}`

| Type | Use |
|------|-----|
| `feature/` | New functionality |
| `bug/` | Bug fixes |
| `chore/` | Maintenance |
| `docs/` | Documentation |
| `hotfix/` | Urgent fixes |

Hierarchy uses `--` (two hyphens) as the separator, not `/`, so a hierarchy slug like `a1b2c3d4--e5f6a7b8` is one git branch segment, not nested directories.
