# Journaling Workflow

## Why Journal

1. Becomes searchable knowledge for future agents
2. Helps with task handoffs
3. Documents decisions and learnings
4. Required before key transitions

## The Tool

Journaling is a single do-tool: `note(text, scope, ...)` (an ADK `FunctionTool`, HTTP POST to `/api/v1/do/note`, no MCP server involved). There is **no** separate `robofleet_journal_*` tool  -  the `scope` argument selects the kind of entry.

| `scope` | Use For |
|---------|---------|
| `note` (default) | General observation |
| `reflect` | End-of-task summary (what done / learned / struggled) |
| `decision` | Architectural decision (context / options / chosen / rationale) |
| `learning` | New knowledge gained |
| `struggle` | Problems and solutions |

## Creating Entries

```python
# General entry
note(
    text="SCAN is better than KEYS for large Redis datasets",
    scope="learning",
    task_id=task_id,
)

# Decision log  -  `decision` scope uses the structured fields
note(
    text="Chose Redis for session storage",
    scope="decision",
    task_id=task_id,
    context="Need fast session lookups, ephemeral data",
    options=[
        {"name": "PostgreSQL", "pros": "durable", "cons": "slower"},
        {"name": "Redis", "pros": "sub-ms reads", "cons": "ephemeral"},
        {"name": "In-memory", "pros": "fastest", "cons": "lost on restart"},
    ],
    chosen="Redis",
    rationale="Sub-millisecond reads; data is ephemeral by design",
    consequences=["Adds Redis as a session dependency"],
)

# Struggle (problem and solution)
note(
    text="Tests failing intermittently; root cause was a setup race condition",
    scope="struggle",
    task_id=task_id,
)
```

`options`, `consequences`, and `next_steps` accept either a list or a single value. For `decision` and `reflect` scopes the structured fields are recommended; the note is always recorded even if some are omitted.

## Required Reflections

Before submitting for QA or completing, write a `reflect` entry:

```python
note(
    text="Implemented rate limiting with Redis",
    scope="reflect",
    task_id=task_id,
    what_done="Redis-backed token bucket on the API edge",
    what_learned="Lua scripts give atomic check-and-decrement",
    what_struggled="Testing concurrent requests deterministically",
    next_steps=["Add a regression test for the boundary case"],
)
```

## Searching Journals

There is no way to search past journal entries yourself under this runtime  -  no dedicated journal-search verb, and no `robofleet_kb_search`/`robofleet_ask_mentor` reachable either (see `docs/rag/workflows/kb-search.md`). You journal forward, for whoever reads it later (a human, or the org-memory institutional-memory briefing when armed)  -  not to search it back yourself.

## Best Practices

1. **Journal as you go** - Don't wait until end
2. **Be specific** - Generic entries are less searchable
3. **Record failures** - They're valuable learning (`scope="struggle"`)
4. **Use the right scope** - `decision` / `reflect` light up the panel views
5. **Include context** - Future searchers need it
