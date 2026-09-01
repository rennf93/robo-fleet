# Journal Tools

There is **no** `robofleet_journal_*` tool. Journaling is a single do-tool: `note` (an ADK `FunctionTool` that HTTP POSTs to `/api/v1/do/note`, no MCP server involved). The `scope` argument selects the entry kind; structured fields are filled per scope. Scopes are `note`, `decision`, `reflect`, `learning`, `struggle` (`robofleet/foundation/policy/journaling.py`'s `Scope` enum) - there is no `handoff` scope in this codebase.

```python
note(
    text: str,                  # always: one-paragraph summary
    scope: str = "note",        # note | decision | reflect | learning | struggle
    task_id: str | None = None, # auto-filled from your active task if omitted
    title: str | None = None,
    # decision-scope fields:
    context: str = "",
    options=None,               # list of {name, pros, cons} (a single dict is ok)
    chosen: str = "",
    rationale: str = "",
    consequences=None,          # list of strings (a single string is ok)
    # reflect-scope fields:
    what_done: str = "",
    what_learned: str = "",
    what_struggled: str = "",
    next_steps=None,            # list of strings (a single string is ok)
)
```

`text` is always required. Missing narrative fields default to a visible placeholder rather than being rejected  -  the note is always recorded.

## Scopes

| Scope | Use For | Structured fields |
|-------|---------|-------------------|
| `note` | General entry | (just `text`) |
| `decision` | Decision log | `context`, `options`, `chosen`, `rationale`, `consequences` |
| `reflect` | Task reflection | `what_done`, `what_learned`, `what_struggled`, `next_steps` |
| `learning` | Learning capture | (just `text`) |
| `struggle` | Problem / blocker | (just `text`) |

## General Entry

```python
note(
    text="SCAN is better than KEYS for large datasets",
    scope="learning",
    title="Redis SCAN vs KEYS",
    task_id=task_id,
)
```

## Decision Log

```python
note(
    text="Chose Redis for session storage over PostgreSQL.",
    scope="decision",
    title="Session storage choice",
    context="Need fast session lookups",
    options=[
        {"name": "PostgreSQL", "pros": "durable", "cons": "slower reads"},
        {"name": "Redis", "pros": "sub-ms reads", "cons": "ephemeral"},
    ],
    chosen="Redis",
    rationale="Sub-ms reads, ephemeral data",
    consequences=["Session loss on Redis restart is acceptable"],
)
```

## Learning

```python
note(
    text="asyncio.gather for parallel calls  -  reduced latency 50%",
    scope="learning",
    title="Parallel async calls",
)
```

## Struggle (Problem / Blocker)

```python
note(
    text=(
        "Tests failing intermittently  -  tried timeout increase and retry "
        "logic; root cause was a race condition in setup."
    ),
    scope="struggle",
    task_id=task_id,
)
```

## Reflection

Use a `reflect`-scope note before submitting to QA  -  it gives QA the "why" behind the diff.

```python
note(
    text="Implemented rate limiting with a Redis-backed sliding window.",
    scope="reflect",
    task_id=task_id,
    what_done="Implemented rate limiting",
    what_learned="Lua scripts give atomicity for the counter increment",
    what_struggled="Testing concurrency deterministically",
    next_steps=["Add a load test for the 100-req boundary"],
)
```

## Reading Journals

Journals are written by `note` and are meant to surface through the knowledge base for later semantic search  -  but there is **no KB-search tool reachable from this runtime**. `robofleet_kb_search`/`robofleet_ask_mentor` exist in the codebase (`robofleet/mcp/optimal_server.py`) but are wired only for the legacy Docker/CLI-container provider path, never for the `ADK_CLOUD_RUN` runtime this fleet's delivery agents actually run on (see `docs/rag/README.md` for the full explanation). In practice: you cannot search past journal entries yourself. The one automatic path is the org-memory "institutional memory" briefing injected at claim time when `org_memory_enabled` is armed (default off) - it surfaces top-K relevant lessons/playbooks in your `context_briefing`, but you never query it directly.
