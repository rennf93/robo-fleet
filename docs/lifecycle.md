# Task Lifecycle

Canonical source: `robofleet/foundation/policy/lifecycle.py`. Every consumer (the Choreographer, the spawn manifest builder, the REST API, tests) reads its behavior from this one module — it validates itself at import time (`_run_all_lifecycle_validators`), so a malformed spec refuses to boot the orchestrator rather than silently drifting from what's enforced.

A `Task` (`robofleet/models/task.py`) is the atomic unit of work. Every task has `acceptance_criteria` (1-7 items, required at creation) and a `status` drawn from the `Status` enum below. State mutation only ever happens through `TaskService` — the model itself carries no transition logic.

## Statuses

```
Status.BACKLOG                 backlog
Status.PENDING                 pending
Status.CLAIMED                 claimed
Status.IN_PROGRESS             in_progress
Status.BLOCKED                 blocked
Status.PAUSED                  paused
Status.VERIFYING               verifying
Status.AWAITING_QA             awaiting_qa
Status.NEEDS_REVISION          needs_revision
Status.AWAITING_DOCUMENTATION  awaiting_documentation
Status.AWAITING_PR_REVIEW      awaiting_pr_review
Status.AWAITING_PM_REVIEW      awaiting_pm_review
Status.AWAITING_CEO_APPROVAL   awaiting_ceo_approval
Status.COMPLETED               completed
Status.CANCELLED               cancelled
```

`COMPLETED` and `CANCELLED` are the only terminal states.

## The state machine

Every row below is a `StatusTransition` in `_STATUS_TRANSITIONS`. "Roles" is either the transition's own `role_constraint`, or — where the table says *per CLAIM_RULES* — resolved by the per-role claim table further down.

| From | To | Verb (`triggered_by_action`) | Roles |
|---|---|---|---|
| `backlog` | `pending` | `activate` | `cell_pm`, `main_pm` |
| `pending` | `claimed` | `claim` | per `CLAIM_RULES` |
| `awaiting_qa` | `claimed` | `claim` | `qa` |
| `awaiting_documentation` | `claimed` | `claim` | `documenter` |
| `needs_revision` | `claimed` | `claim` | per `CLAIM_RULES` (dev, cell_pm, main_pm) |
| `awaiting_pr_review` | `claimed` | `claim` | `pr_reviewer` |
| `claimed` | `in_progress` | `start` | dev/qa/doc/pm/pr_reviewer |
| `in_progress` | `blocked` | `block` | dev/qa/doc/pm |
| `in_progress` | `paused` | `pause` | dev, cell_pm, main_pm |
| `blocked` | `in_progress` | `unblock` | `cell_pm`, `main_pm` |
| `blocked` | `pending` | `unblock` | `cell_pm`, `main_pm` (a never-claimed task blocked pre-claim has no branch) |
| `paused` | `in_progress` | `resume` | dev/qa/doc/pm |
| `in_progress` | `verifying` | `submit_verification` | `developer` |
| `verifying` | `awaiting_qa` | `submit_qa` | `developer` |
| `in_progress` | `completed` | `pr_review_done` | `pr_reviewer` (inbound external/fork review task finishes) |
| `awaiting_qa` | `awaiting_documentation` | `qa_pass` | `qa` |
| `awaiting_qa` | `needs_revision` | `qa_fail` | `qa` |
| `awaiting_documentation` | `awaiting_pm_review` | `docs_complete` | `documenter` |
| `in_progress` | `awaiting_pr_review` | `submit_for_review` | `cell_pm`, `main_pm` |
| `awaiting_pr_review` | `awaiting_pm_review` | `pr_pass` | `pr_reviewer` |
| `awaiting_pr_review` | `needs_revision` | `pr_fail` | `pr_reviewer` |
| `awaiting_pm_review` | `completed` | `complete` | `cell_pm`, `main_pm` |
| `awaiting_pm_review` | `needs_revision` | `request_changes` | `cell_pm`, `main_pm` |
| `awaiting_pm_review` | `awaiting_ceo_approval` | `escalate_to_ceo` | `main_pm`, `product_owner`, `head_marketing` |
| `blocked` | `awaiting_ceo_approval` | `escalate_to_ceo` | `main_pm`, `product_owner`, `head_marketing` |
| `awaiting_ceo_approval` | `completed` | `ceo_approve` | `ceo` |
| `awaiting_ceo_approval` | `needs_revision` | `ceo_reject` | `ceo` |
| `awaiting_ceo_approval` | `pending` | `ceo_reject_to_pool` | `ceo` (branchless coordination root/umbrella only) |
| `in_progress` | `awaiting_pm_review` | `submit_pm_review` | pm/qa/doc/dev (non-code coordination tasks) |
| any non-terminal | `cancelled` | `cancel` | `cell_pm`, `main_pm`, `ceo` (from `awaiting_ceo_approval`: `ceo` only) |

The full source→target adjacency also lives at runtime as `STATUS_GRAPH` (built by `_build_status_graph()`), a `dict[Status, frozenset[Status]]`.

## Claim rules (`CLAIM_RULES`)

`claim`'s atomic-action `source_statuses` is the union across every claimant role; this table narrows by role — the actual authority check:

| Role | May claim from |
|---|---|
| `developer` | `pending`, `needs_revision` |
| `qa` | `awaiting_qa` |
| `documenter` | `pending`, `awaiting_documentation` |
| `cell_pm` | `pending`, `needs_revision` |
| `main_pm` | `pending`, `needs_revision` |
| `pr_reviewer` | `pending`, `awaiting_pr_review` |
| `product_owner`, `head_marketing`, `auditor`, `ceo` | none — these roles never claim |

`awaiting_pm_review` is deliberately absent for `cell_pm`/`main_pm`: a task there already passed the PR gate and is waiting on the owning PM's merge decision (`complete` / `request_changes`), not re-planning. A PM re-entering its own `awaiting_pm_review` task is steered by the choreographer's `i_will_plan` re-entry contract straight to `complete`/`request_changes` with no claim and no status change — a prior revision that *did* allow the claim let a respawned PM legally re-claim, reset to `in_progress`, and re-run the whole `submit_up → pr_pass → awaiting_pm_review` cycle forever (one production task looped 11 times across 37 spawns in the code's own inherited incident notes).

`needs_revision` is claimable by both `developer` and the PM roles: QA/PR-gate failure or a CEO rejection lands a *leaf* task back with the original developer, but a *PM-owned coordination task* (the assembled cell→root or root→master PR) has no developer — the owning PM re-claims via `i_will_plan` to revise the plan and re-delegate the fix.

## Team scoping and claim-time guards

Every claimable `ActionSpec` sets `needs_team_match=True`: a `backend` agent cannot act on a `frontend` task, except for the org-wide roles (`main_pm`, `ceo`, `product_owner`, `head_marketing`, `auditor`, `pr_reviewer`), which are exempt (`_ORG_WIDE_ROLES`).

Before the spec gate is even reached, `claim_guards.py` runs concurrency invariants the lifecycle spec doesn't model:

- **`already_active_guard`** — an agent already holding a `claimed` / `in_progress` / `verifying` / `blocked` task may not claim a second one.
- **`paused_tasks_guard`** — an agent with a *different* paused task must resume it before claiming new work.
- **`sequence_held_guard`** — see "Sequence is the bar" below.
- **`unmet_dependency_guard`** — a task with non-terminal `dependency_ids` cannot be claimed.
- **`project_budget_exceeded_guard`** — refuses a *work-starting* claim (`i_will_work_on` / `i_will_plan` only — review/doc/gate/inbound-PR claims are exempt) once the task's project has spent its `monthly_budget_usd` cap for the calendar month. Feature-flagged (`ROBOFLEET_TASK_BUDGETS_ENABLED`); inert when `monthly_budget_usd` is null.
- **PM concurrency exemption** — `already_active`/`paused` are skipped for `cell_pm`/`main_pm`: a PM plans and delegates many roots in parallel, so only a genuine sequence/dependency hold blocks a PM's claim, never "you already have a task open."

### Sequence is the bar

A task with a parent and effective sequence N (`COALESCE(sequence, 0)`) cannot be claimed while any same-parent sibling with a strictly lower effective sequence is still non-terminal — independent of `dependency_ids` for a MegaTask batch root-subtask (`TaskService._claim_blocked_by_sequence` in `robofleet/services/task.py`). Ties run in parallel; sequence `0` and parentless tasks are unaffected; cancelled/completed siblings never block. Outside a batch root-subtask, the hold is dependency-graph-aware (`sequence_blocker_id`): a lower-sequence sibling only blocks when it's a real transitive predecessor via `dependency_ids ∪ completed_dependency_ids` — an unrelated sibling that merely shares a lower raw number never phantom-blocks. A rejected claim on this guard surfaces as the distinct `Envelope.sequence_held` shape (not a generic `invalid_state`), naming the blocking sibling.

## Git: branches, commits, PRs

**Branch naming** (`robofleet/templates/git/branch.py`, `build_branch_name`): `{type}/{team}/{root8}--{sub8}--{subsub8}--{subsubsub8}`, where each `*8` segment is the first 8 chars of that ancestor task's UUID and `--` separates hierarchy levels (git can't have both `foo` and `foo/bar` as branch names, so `/` inside the hierarchy would collide). `type` is one of `feature`, `bug`, `chore`, `docs`, `hotfix` (`BRANCH_TYPES`, `robofleet/templates/git/constants.py`). Max depth is 4 (`MAX_TASK_DEPTH`) — MegaTask's umbrella → root-subtask → cell task → dev subtask hierarchy. `branch_name` is set on `claim`; the same clone is reused across an agent's tasks, so push/PR operations key on the task's *recorded* branch name, not whatever the clone happens to be checked out to.

**Commit convention** (`ContentActions.commit`, `robofleet/services/gateway/content_actions.py`): only `developer` and `documenter` roles may commit (`_COMMIT_ALLOWED_ROLES`). Every commit message is rewritten server-side to `[{task_id[:8]}] {subject}` before it reaches git (`canonical_prefix` in the `commit` do-tool) — the caller's raw message is stripped of any task-id prefix and AI-attribution boilerplate first.

**PR flow**: PRs open *before* QA review, never after — so QA reviews the real GitHub diff and every downstream PM/CEO decision rides a PR that already exists. `open_pr` (dev-only) is legal from `in_progress` / `verifying` / `awaiting_qa` / `awaiting_documentation` / `needs_revision` (`PR_OPEN_STATES`); it requires ownership, >=1 commit, and no PR already open, then pushes the branch and calls the GitHub/forge `create_pr` side effect.

## The in-path PR-review gate (assembled PRs)

Distinct from the inbound-external-PR reviewer surface (`claim_pr_review` / `post_pr_review`, for PRs the org didn't author): this gate reviews the org's *own* assembled cell→root and root→master PRs before a PM merges them.

1. **Cell PM** calls `submit_up` on an in-progress cell coordination task. The verb's `pre_side_effects=("create_pr",)` opens the cell→root PR *before* the composed `submit_for_review` transition runs (so the downstream `pr_created` gate is already satisfied) — `in_progress → awaiting_pr_review`.
2. **Main PM** calls `submit_root` on the root task the same way (`pre_side_effects=("create_root_pr",)`), with the extra precondition `PRECONDITION_ROOT_NOT_CODE` — a Main-PM root is always planning-typed, never `code`.
3. A **PR reviewer** (`pr_reviewer` role) calls `claim_gate_review` — claims the task *without* transitioning it (status stays `awaiting_pr_review`, mirroring QA's `claim_review`), and gets the assembled diff back inline.
4. **`pr_pass`** → `awaiting_pm_review` (the owning PM can now merge). `pr_pass` additionally refuses (`_pr_pass_blocked` in `choreographer/pr_gate.py`) while the assembled PR's own head-commit CI is failing, pending, or unresolvable, or while a broken toolchain / unresolved architectural-convention violation exists — a repo with no CI configured at all passes through with an evidence note; a CodeQL failure entirely outside the task's declared `intends_to_touch` scope is also treated as pass-through, not a block.
5. **`pr_fail`** → `needs_revision`, routed back exactly like a QA fail, carrying structured findings (see below).

Reviewers are assigned per cell (`be-pr-reviewer`, `fe-pr-reviewer`, `ux-pr-reviewer`) plus one org-wide overflow reviewer (`cell-pr-reviewer-2`) and one reviewer for the root→master gate and inbound external PRs (`pr-reviewer-1`) — see `docs/agents.md`.

## Merge and CEO approval

`complete` dispatches by caller role (`Choreographer.complete` in `_impl.py`):

- **`cell_pm_complete`** — merges the leaf/cell PR into the parent branch (resolved via `resolve_parent_branch`, the real parent task's own `branch_name` — not derived from the branch-name string), then transitions `awaiting_pm_review → completed` directly. Idempotent: if the PR is already merged on the forge, the merge call is skipped and the transition proceeds straight through.
- **`main_pm_complete`** — for a branch-bearing root (already `awaiting_pm_review` via `submit_root` → `pr_pass`), it does **not** complete the task itself: it calls `TaskService.escalate_to_ceo`, moving `awaiting_pm_review → awaiting_ceo_approval`. For a branchless coordination root (no repo/PR — a product fan-out or umbrella), it first walks `in_progress → awaiting_pm_review` (`submit_pm_review`), then does the same CEO escalation. Either way, `assigned_to` is cleared afterward — the CEO acts through the panel, not as a spawned agent chasing the task.

**CEO approval** is a human action over the REST API (`POST /api/tasks/{id}/ceo-approve`, `robofleet/api/routes/tasks.py`), not a gateway verb — the CEO never runs inside the agent fleet. `ceo_approve` requires a substantive note (>=20 chars) and — unless the task is PR-waived — that the task's `WorkSession.pr_status == "merged"`; the CEO merges the PR first (`POST /api/tasks/{id}/approve-and-merge`, or a separate merge call) before approving. `ceo_reject` requires a non-trivial `reason`, writes it as one `origin=ceo` `blocker` finding into the revision-findings ledger, and routes `awaiting_ceo_approval → needs_revision` — except a branchless coordination root, which has no developer to revise it and instead goes to `pending` (`ceo_reject_to_pool`) for the Main PM to re-plan.

## PR-waiver (report-only work)

A project-bound cell/root task assembled entirely from report-only children (zero commits on its branch relative to its resolved parent) would otherwise 422 against the forge's "no commits between" error when `submit_up` / `submit_root` tries to open a PR. `VerbRunner._maybe_waive_pr_creation` detects this (via `GitService.is_behind_base`'s `ahead` count) *before* dispatching `create_pr`/`create_root_pr`, stamps a `pr_waived` marker (`robofleet/foundation/policy/content/markers.py`) plus a transition note, and reroutes the task straight to `submit_pm_review` (skipping the PR gate, since there is no diff for a reviewer to check). Every downstream PR-required gate (`submit_pm_review`'s PR-created check, the merge guard, `complete`'s work-session-merged check, the CEO-escalation gate) is exempted for a `pr_waived` task the same way a branchless coordination root is exempted. On a genuine git/network error the waiver check fails *open* (proceeds with the normal `create_pr` attempt) rather than silently waiving a PR a retry would have created fine.

## The revision-findings ledger

QA fail (`fail_review`), the PR gate's `pr_fail`, the PM's `request_changes`, and the CEO's `ceo_reject` all take structured `findings: list[dict]` (`robofleet/services/gateway/choreographer/findings.py`), validated into a `Finding` model (`robofleet/foundation/policy/content/models.py`):

| Field | Notes |
|---|---|
| `file` | optional, repo-relative, no `..` traversal, must look like a path |
| `line` | optional, `>=1` |
| `severity` | `blocker` \| `major` \| `minor` \| `nit` |
| `criterion` | optional; must match an acceptance-criterion id or its exact text |
| `expected` | required, non-trivial |
| `actual` | required, non-trivial |
| `fix` | optional, a described change (never a literal patch) |
| `evidence` | optional, a verbatim excerpt |

Legacy `issues: list[str]` is still accepted for one release — each string shims into a file-less `severity=major` finding (deprecation-logged) — and merges with `findings` rather than either silently dropping the other. A findings list over 10 in one call is hard-rejected (`FINDINGS_HARD_CAP`); over 5 gets a non-blocking nudge (`FINDINGS_NUDGE_COUNT`).

Every finding is inserted as one append-only row into the `task_review_findings` table (`origin` = `qa` \| `pr_gate` \| `pm` \| `ceo`, `round` = `revision_count + 1` read *before* the transition, `status` progresses `open → addressed → verified` \| `waived`), rendered deterministically as `[F-<id8>] file:line (severity) — expected → actual → fix` into the producing role's own note slot (`qa_notes` / `pr_reviewer_notes` / `pm_notes`).

**Resolution**: `i_am_done` / `submit_up` / `submit_root` all take `resolved_findings: [{finding_id, commit?, note?}]` — every OPEN finding on the task must be named (fuzzy 8-char-prefix match against the `[F-id8]` rendering) before the submit is accepted. The reviewing verb that follows (`pass_review` / `pr_pass` / `complete`) bulk-verifies its own origin's `addressed` findings in the same transaction as the pass. The Auditor's `waive_finding` verb can waive an open `minor`/`nit` finding with a required note; `blocker`/`major` findings can never be waived, only fixed.

## Per-AC verification (not a gestalt pass)

`pass_review` (QA) requires `criteria_verified`: one `{criterion, evidence}` entry per acceptance criterion on the task, matched by id or exact text — every criterion must be named with concrete evidence or the pass is refused (`_qa_pass_final_gates` in `choreographer/qa.py`). `delegate` (a PM creating a subtask) similarly requires `covers_parent_criteria` mapping onto the parent's real acceptance criteria; an unresolvable reference is rejected by name rather than silently dropped.

## Envelope-level errors specific to lifecycle transitions

Beyond the generic error shapes documented in `docs/gateway.md`, two are lifecycle-specific:

- **`self_review`** — an atomic action with `self_review_block=True` (`qa_pass`, `qa_fail`, `docs_complete`, `pr_pass`, `pr_fail`) refuses when the acting agent's slug matches the task's `original_developer` marker.
- **`sequence_held`** — see "Sequence is the bar" above; distinct from `invalid_state` so a stably-held reclaim isn't misread as a concurrent race.

## Inert on this deployment

`robofleet/config.py` still carries the full set of inherited, default-off autonomy engines this codebase's history built up (self-heal CI watch, dependency-update bot, docs-sync, gated release manager, org-memory loop, sandboxed dev DB provisioning, an X/Twitter posting engine, a Telegram notifications bridge, an env-branch promotion ladder, task/project cost budgets, Fable-mode doctrine). They are real, testable code paths, but every one of them is a `False`-by-default config flag with no demo-path wiring — none of them run on this deployment.
