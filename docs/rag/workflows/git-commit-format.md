# Git Commit Format

**See `docs/rag/workflows/git-commits.md` for the full workflow  -  this file covers only the message format.** The real format, verified against `robofleet/services/gateway/content_actions.py`'s `commit()` action and `robofleet/services/gateway/commit_validator.py`, is much simpler than a template with a body/footer/links block:

```
[{task_id:8}] {your subject}
```

Example: `[a1b2c3d4] Add rate limiting endpoint`

You write the subject; the gateway strips any `[task-id]` you included yourself and re-prefixes with the canonical 8-char task id.

**Validated (enforced), via `commit_validator.validate_commit_message`:**
- Non-empty
- At least `commit_subject_min_chars` (default 20) characters
- Not a single banned word (case-insensitive): `wip`, `tmp`, `asdf`, `oops`, `fix`, `update`, `change`, `stuff`, `things`

**Not enforced  -  a soft hint only:** Conventional-Commits shape (`type(scope): subject`, e.g. `feat(api): ...`). A subject that doesn't match `^(feat|fix|chore|docs|refactor|test|perf|build|ci)(\(scope\))?:\s+.+$` still succeeds; the response just carries a hint suggesting that shape. There is no required `type`, no body template, no footer with task/root/agent links  -  write a real, substantive subject line and you're done.

Only `developer` and `documenter` roles may commit (`commit` is not in any other role's manifest).

## How to commit

```python
commit(
    message="Add rate limiting endpoint",
    files=["robofleet/api/routes/rate.py", "tests/integration/test_rate.py"],
    # files is optional; defaults to all staged + modified tracked files
)
```

There is no `git_commit`-via-shell path and no separate `push` tool the model calls directly  -  `commit` (a do-tool, HTTP POST to `/api/v1/do/commit`, no MCP) stages, commits, and pushes in one call.
