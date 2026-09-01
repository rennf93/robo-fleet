# Common Issues

## Permission Denied

**Error**: "Not authorized for this action"

**Cause**: Your role doesn't have permission

**Check Permissions**:
| Action | Allowed Roles |
|--------|---------------|
| Create / delegate task | PM only (Cell PM, Main PM) |
| Cancel task | PM, CEO |
| Pass/fail QA | QA only |
| Complete docs | Documenter only |
| Complete task | PM only |
| Send notification (`notify`) | PM, Board |

**Solution**: Request appropriate role to perform action

## Task Stuck in Status

**Problem**: Task won't transition

**Causes**:
1. Missing required fields
2. Waiting on parallel action
3. Invalid transition attempted

**Check**:
- Branch exists?
- For `awaiting_pm_review`: both `docs_complete` AND `pr_created`?
- Is transition valid from current status?

## Notification Not Received

**Problem**: Expected notification didn't arrive

**Causes**:
1. Sender doesn't have notification permission
2. Notification filtering
3. Already acknowledged

**Solutions**:
- Check `notify_list()` for all notifications
- Verify sender has PM/Board role
- Check if already acknowledged via `notify_get(notification_id)`

## Escalation Not Routing

**Problem**: Escalation went to wrong person

**Cause**: `escalate_up` auto-routes to your escalation target

**Chain**:
```
Cell members → Cell PM → Main PM → Product Owner → CEO
```

Cannot skip levels or choose target. (Only Main PM / Board call `escalate_to_ceo`; cell members and Cell PMs use `escalate_up`.)

## You Have No Local Test/Lint/Type-Check Tool

**Problem**: You want to verify your work compiles/passes before submitting, but there is nothing to run

**Cause**: Under the ADK runtime, a delivery agent has no Bash/shell tool at all - not `pytest`, not `ruff`, not `mypy`, not `pnpm`. Your only tools are the flow/do verbs (`robofleet/agent/gateway_shim.py`) and the seven file/git functions in `robofleet/agent/git_tools.py`.

**Solution**: Read your own diff back with `read_file` before submitting. The real quality signal is the project's own CI, which runs against your pushed branch after `open_pr` - QA's review and (when armed) the possibilities-matrix fast path's CI-status check are what actually gate the work, not anything you run yourself.

## Lost Context After Pause

**Problem**: Resuming task, forgot context

**Solutions**:
- Read `quick_context` field on task (returned inline by `give_me_work`/`evidence`)
- `resume(task_id)` - your claim briefing carries the task's current state
- There is no `robofleet_get_proactive_context` or any other separate context-fetch tool under this runtime; `evidence(task_id)` is the one do-tool that assembles a fresh evidence brief (AC coverage, prior findings, commits, handoff) on demand

## Documentation Path Confusion

**Problem**: Unsure where to write documentation

**Solution**: There is no `robofleet_docs_write` tool and no automatic path/dedup handling under this runtime (see `docs/rag/tools/kb-tools.md`). Write the file straight into the project's worktree with `write_file(rel_path, content)` (`robofleet/agent/git_tools.py`) at a path that makes sense for the project's own docs convention, then `commit(message, files=[...])`. `read_file` an existing doc first if you suspect one already covers the topic - there is no automatic dedup, so duplicating one is on you to avoid.

## A2A Message Not Delivered

**Problem**: Sent a `dm` but no response

**Check**:
1. Is the recipient in your **own cell**? Cross-cell `dm` is denied by policy  -  route through your Cell PM via `escalate_up(task_id, reason)`.
2. Use the right slug  -  recipient slugs come from your known team/cell roster (see `docs/rag/architecture/org-structure.md`'s Cells table), not a runtime discovery call.
3. Did you include `task_id`? It anchors the message to the work.

**Solutions**:
- Same-cell peer: `dm(recipient="be-qa", text="...", task_id="...")`
- Anything cross-cell or needing PM action: `escalate_up(task_id, reason)`

## Cross-Cell Message Denied

**Error**: A `dm` to an agent outside your cell is rejected by policy

**Cause**: Direct A2A is same-cell only  -  there is no cross-cell `dm`

**Solution**: Escalate up the chain. Use `escalate_up(task_id, reason)` so your Cell PM can coordinate with the other cell's PM.
