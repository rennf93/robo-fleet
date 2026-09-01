# The Organization

Canonical source: `robofleet/foundation/identity.py`, the single `AGENTS: dict[str, AgentRow]` registry — every other consumer (the lifecycle spec, `role_config.py`, the seed data, the orchestrator's team map) reads from here. Adding an agent means editing exactly this file.

## Headcount

The registry (`AGENTS`) holds **28 rows**: one `system` sentinel (used only as the `from_agent` on orchestrator-generated audit rows, never spawned) plus **27 real identities** — **1 human** (the CEO) and **26 AI agents**. Counted directly from the registry, not from any prior marketing figure:

```
non-system entries: 27
human:  ['ceo']
ai count: 26
```

## Structure

```
CEO (human, board team, panel-only — never spawned as a container)
  |
  +-- Intake (intake-1, role=prompter)      — on-demand: interviews the CEO, drafts a task
  +-- Secretary (secretary-1, role=secretary) — on-demand: CEO's chief-of-staff, gated CEO directives
  +-- PR Reviewer, root gate (pr-reviewer-1) — reviews inbound external/fork PRs + the root->master gate
  |
  +-- Board (product-owner, head-marketing, auditor)
       |
       +-- Main PM (main-pm) — coordinates across all three cells
            |
            +-- Backend cell   (be-dev-1, be-dev-2, be-qa, be-pm, be-doc, be-pr-reviewer)
            +-- Frontend cell  (fe-dev-1, fe-dev-2, fe-qa, fe-pm, fe-doc, fe-pr-reviewer)
            +-- UX/UI cell     (ux-dev-1, ux-dev-2, ux-qa, ux-pm, ux-doc, ux-pr-reviewer)
            |
            +-- cell-pr-reviewer-2 — org-wide overflow reviewer for any cell's gate
```

Each of the three delivery cells is 6 agents: 2 developers, 1 QA, 1 PM, 1 documenter, 1 PR reviewer — 18 cell agents total, plus Main PM, the three Board seats, the root/inbound PR reviewer, the overflow gate reviewer, Intake, and Secretary = 26.

## Every agent, verbatim from the registry

| Slug | Role | Team | Human |
|---|---|---|---|
| `ceo` | `ceo` | `board` | **yes** |
| `be-dev-1`, `be-dev-2` | `developer` | `backend` | no |
| `be-qa` | `qa` | `backend` | no |
| `be-pm` | `cell_pm` | `backend` | no |
| `be-doc` | `documenter` | `backend` | no |
| `be-pr-reviewer` | `pr_reviewer` | `backend` | no |
| `fe-dev-1`, `fe-dev-2` | `developer` | `frontend` | no |
| `fe-qa` | `qa` | `frontend` | no |
| `fe-pm` | `cell_pm` | `frontend` | no |
| `fe-doc` | `documenter` | `frontend` | no |
| `fe-pr-reviewer` | `pr_reviewer` | `frontend` | no |
| `ux-dev-1`, `ux-dev-2` | `developer` | `ux_ui` | no |
| `ux-qa` | `qa` | `ux_ui` | no |
| `ux-pm` | `cell_pm` | `ux_ui` | no |
| `ux-doc` | `documenter` | `ux_ui` | no |
| `ux-pr-reviewer` | `pr_reviewer` | `ux_ui` | no |
| `main-pm` | `main_pm` | `main_pm` | no |
| `product-owner` | `product_owner` | `board` | no |
| `head-marketing` | `head_marketing` | `board` | no |
| `auditor` | `auditor` | `board` | no |
| `pr-reviewer-1` | `pr_reviewer` | `board` | no |
| `cell-pr-reviewer-2` | `pr_reviewer` | `board` | no |
| `intake-1` | `prompter` | `board` | no |
| `secretary-1` | `secretary` | `board` | no |

`Role` and `Team` are separate enums (`robofleet/foundation/identity.py`): `Role` = `developer`, `qa`, `documenter`, `cell_pm`, `main_pm`, `product_owner`, `head_marketing`, `auditor`, `pr_reviewer`, `prompter`, `secretary`, `ceo`, `system`. `Team` = `backend`, `frontend`, `ux_ui`, `board`, `main_pm`, `fullstack`, `marketing` (legacy, unused by any current agent), `system`. `CELL_TEAMS` (`backend`/`frontend`/`ux_ui`) is the subset that is "a delivery cell" — distinct from board/main_pm/system.

## Role responsibilities

Descriptions below are distilled from the role's own operating prompt (`agents/prompts/roles/*.md`) plus its verb/tool grant in `robofleet/services/gateway/role_config.py` — not from any external marketing copy.

**Developer** (`developer`) — implements. Claims a task via `i_will_work_on`, writes code, commits, pushes, opens a PR, and submits for QA (`i_am_done`). Never merges, never reviews its own work, never delegates. Read/write filesystem access is scoped to its own per-agent clone.

**QA** (`qa`) — reviews the PR diff against acceptance criteria, reads the developer's journal for intent, and passes or fails with per-criterion evidence (`criteria_verified`). Never writes code, never merges; the gateway rejects a QA claim where the reviewing agent was the task's original developer (self-review block).

**Documenter** (`documenter`) — writes production documentation (README, API reference, architecture notes) onto the same branch the PR already covers, once QA has passed the code. Does not re-implement or critique the code; commits doc files, calls `i_documented`.

**Cell PM** (`cell_pm`) — one per delivery cell. Receives a task from the Main PM, decomposes it into the fewest subtasks the work genuinely needs, delegates each to a developer in its own cell (`delegate`), merges what comes back (`complete`), and opens the cell→root PR (`submit_up`). Never writes code, never claims a code task (the gateway rejects it), never merges to master.

**Main PM** (`main_pm`) — one seat, org-wide (`main-pm`). Receives a root task, delegates one subtask per participating cell to that cell's PM, merges what the cell PMs submit into the root branch, and opens the root→master PR (`submit_root`). On completion it escalates the root to the CEO rather than merging it — the CEO is the only actor that ever touches master.

**Product Owner** (`product_owner`) and **Head of Marketing** (`head_marketing`) — Board roles. Triage tasks at the org level and escalate strategic decisions to the CEO (`escalate_to_ceo`). Sit above the Main PM but never communicate with cell PMs directly, never execute, never delegate, never write code. Each also carries a set of `propose_*` do-tools for originating held, CEO-gated content (roadmap items, bug-hunt findings, market briefs, etc.) — see "Inert on this deployment" below.

**Auditor** (`auditor`) — silent, read-only observer. Its only outward tools are `note`, `evidence`, and `dm`/`read_a2a` (to reply in-thread when the CEO opens a direct message with it — it never initiates). It carries a bounded playbook-curation surface (`approve_playbook`/`reject_playbook`/`archive_playbook`) and `waive_finding` (waiving a `minor`/`nit` review finding).

**PR Reviewer** (`pr_reviewer`) — five agents share this role: one per cell for the in-path assembled-PR gate (`be-pr-reviewer`, `fe-pr-reviewer`, `ux-pr-reviewer`), one org-wide overflow gate reviewer (`cell-pr-reviewer-2`), and one that additionally reviews the root→master gate plus every inbound external/fork PR (`pr-reviewer-1`). Read-only: reads diffs, records findings, never writes code, never merges. Its only initiation target (via `dm`) is its owning cell/main PM.

**Intake** (`prompter`, slug `intake-1`) — human-only, on-demand. Talks to exactly the CEO, reads the actual codebase for its scoped repo(s), and drafts a well-formed task (or a MegaTask batch) the CEO can launch. Never writes code, merges, or creates tasks directly — it drafts, the CEO confirms.

**Secretary** (`secretary`, slug `secretary-1`) — human-only, on-demand chief-of-staff. Reads company state (task queue, agent/cell status, the charter) freely; acts only on explicit CEO instruction, and bounces high-impact directives back for a confirm before executing.

**CEO** (`ceo`) — the one human. Never spawned as a container; approves/rejects/cancels tasks in `awaiting_ceo_approval` and merges to master through the panel (`robofleet/api/routes/tasks.py`), not through the gateway. An agent can never initiate contact with the CEO — only the CEO opens a conversation (A2A DM), and Intake/Secretary each run their own dedicated chat surface instead of the gateway verb path.

## Human-driven vs. agent-driven

`is_human_only_role` (`robofleet/foundation/identity.py`) names exactly three roles as human-facing and never spawned as a delivery-lifecycle container: `ceo`, `prompter`, `secretary`. `WORKTREE_AUTHOR_ROLES` — the roles whose task worktree may legitimately hold committed-unpushed work — is `developer` and `documenter` only; every other role only ever reads a task's worktree.

Intake and Secretary are not one-shot task-lifecycle agents like the other 24: `robofleet/agent_sdk/secretary_driver.py` describes the Secretary as "a long-lived conversational agent like Intake; it reuses the generic chat machinery" — a persistent chat session over the CEO's own conversation, distinct from the one-shot `give_me_work → ... → i_am_done`-style task loop every delivery role runs.

## Reporting and escalation

- A developer/QA/documenter that is stuck calls `i_am_blocked`, which transitions its task to `blocked` and is a PM's problem to resolve (`unblock`) or push further up (`escalate_up`, `escalate_to_ceo`).
- A Cell PM's own escalation path is `escalate_up` (to its `escalation_target`, effectively the Main PM) or directly `escalate_to_ceo`.
- The Main PM, Product Owner, and Head of Marketing are the only roles that can call `escalate_to_ceo` — the sole gateway-side path onto `awaiting_ceo_approval`.
- The Board (`product_owner`, `head_marketing`, `auditor`) sits organizationally above the Main PM for strategic escalation, but never issues instructions down to a cell PM directly — Board feedback for a cell routes through the CEO or the Main PM.
- A Board role can never be assigned a Main-PM coordination root (no `unblock` verb — such a hand-off would deadlock); reassignment/escalation onto a coordination root is diverted back to the pool for a role-matched Main-PM reclaim.

## Communication

Agents coordinate primarily through task state and task detail fields, not a channel/session backbone. Two comms primitives sit alongside that:

- **A2A** (`dm` / `read_a2a`) — direct peer-to-peer messaging, same-cell only for most roles. The CEO is the one asymmetric participant: it can open a 1:1 DM with any DM-capable agent from the panel at any time, but no agent can ever initiate to the CEO — only reply in-thread once the CEO has opened one.
- **Notifications** (`notify`, ack-required) — formal, sent by PM/Board roles; every role with inbox access carries `notify_list`/`notify_get`/`notify_ack`/`read_messages` so a soft "you have unread notifications" block on `i_am_idle` is always satisfiable.

The Auditor and PR Reviewer carry `dm`/`read_a2a` only for CEO-reachability (replying in-thread), never to initiate peer-to-peer contact on their own — enforced at `agents_config.can_a2a_direct`, not merely by prompt convention.

## Inert on this deployment

The Product Owner and Head of Marketing each carry a set of `propose_*` do-tools (`propose_roadmap`, `propose_bug_hunt`, `propose_gap_fill`, `propose_rebalance`, `propose_friction_fixes` for the PO; `propose_feature_spotlight`, `propose_market_brief`, `propose_messaging_fixes`, `propose_editorial_post`, `propose_campaign`, `propose_conversation_replies` for HoM), and the Auditor carries `propose_postmortem`, `propose_quality_report`, `propose_playbook_drafts`. These back a registry of periodic "Board Program" autonomy cycles (weekly roadmap review, bug-hunt sweeps, market briefs, an X/Twitter posting queue, etc.) inherited from this codebase's earlier product. Every one of them is gated by a per-program settings-store toggle that defaults off, and every artifact they'd produce is held for explicit CEO approval, never auto-materialized — so the tools exist in the manifest but have nothing armed to trigger them on this deployment.
