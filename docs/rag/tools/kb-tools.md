# Knowledge Base Tools

## Search and Query

| Tool | Purpose |
|------|---------|
| `robofleet_kb_search` | Semantic search |
| `robofleet_rag_query` | AI-synthesized answer |
| `robofleet_ask_mentor` | Conversational help |
| `robofleet_kb_stats` | Index statistics |

## Semantic Search

```python
robofleet_kb_search(
    query="rate limiting redis",
    top_k=5,
    project="robofleet-api",
    index_types=["code", "docs"],
)
```

## AI-Generated Answers

```python
robofleet_rag_query(query="How does authentication work?", top_k=5)
```

## Mentor (Conversational)

```python
response = robofleet_ask_mentor(question="How do I handle auth?", domain="coding")

# Follow-up
robofleet_ask_mentor(
    question="What about refresh tokens?", conversation_id=response["conversation_id"]
)
```

## Documentation Writing (Documenter, Cell PM)

```python
# Write/update documentation (auto-dedup via RAG)
robofleet_docs_write(
    {
        "task_id": "task-uuid",
        "filename": "api-endpoints.md",
        "doc_type": "api",  # api, qa, guide, readme, changelog, architecture, design
        "title": "API Endpoints",
        "content": "# API Endpoints\n\n...",
    }
)

# List docs for a task
robofleet_docs_list(task_id="task-uuid")

# Read a doc
robofleet_docs_read(path="backend/api/endpoints.md")
```

**SMART DEDUPLICATION**: `robofleet_docs_write` searches RAG for similar existing docs. If high-similarity match found, updates instead of creating duplicate.

**LIVE-WRITE PROVENANCE**: a doc indexed via `robofleet_docs_write` (or captured from your workspace at `i_documented`) is written mid-task, before your task's PR merges — it may describe an API/contract that doesn't exist yet on the deployed tree. It's indexed with `provenance: "live_write"`, and any `robofleet_kb_search` / `robofleet_ask_mentor` / `robofleet_rag_query` hit built from it comes back with an appended line: `[caveat: written during in-flight work — verify the contract exists on the deployed tree/git before relying on it]`. Docs picked up by the repo-tree scan (`docs/rag`, `docs/map`, or a manual/startup reindex) carry `provenance: "repo_tree"` instead and render with no caveat.

**The caveat does NOT auto-clear on merge.** There is no lifecycle hook wiring a task's PR merge back into the KB, and the periodic re-scan only walks `docs/rag` + `docs/map` — siblings of the team dirs `robofleet_docs_write` actually targets, so it never revisits a `live_write` doc. The marker persists until that doc's content is re-indexed from the repo tree — a startup reindex, or the operator-only `robofleet_reindex_all` escape hatch — merged or not. So read a caveated hit as "verify against git", not "this is unmerged": don't assume a caveat's absence means merged, and don't assume its presence means still-open. Check the referenced PR/branch before building against it either way.

## Bulk Indexing

```python
# Index code (PM, Developer)
robofleet_kb_index_code(sources=["src/**/*.py"], project="robofleet-api")

# Index docs (PM, Documenter) - for bulk/explicit indexing
# Note: robofleet_docs_write() auto-indexes when writing
robofleet_kb_index_docs(sources=["docs/**/*.md"], project="robofleet-api")
```

## Error Tracking

```python
# Search for similar errors
robofleet_search_error(error_message="Redis connection timed out", context="startup")

# Record solution
robofleet_record_error_solution(
    error_message="Redis connection timed out",
    solution="Added retry with backoff",
    worked=True,
)
```

## Decision Tracking

```python
# Check for similar decisions
robofleet_check_decision(topic="session storage")

# Record decision
robofleet_record_decision(
    params={topic: "Session storage", decision: "Use Redis", rationale: "Sub-ms reads"}
)
```

## Standards & Validation

### Get Standards

```python
robofleet_get_standards(domain="coding", language="python")
```

**Domains:** `coding`, `security`, `workflow`, `architecture`

### Validate Action (LLM-Based)

Uses LLM to check code/context against organizational standards.

```python
result = robofleet_validate_action(
    action_type="create_endpoint",
    context="""
def create_user(email, password):
    user = User(email=email, password=password)
    db.add(user)
    return user
""",
)
```

**Returns:**

```json
{
  "allowed": false,
  "violations": [
    {
      "rule_id": "SEC-001",
      "rule_title": "Password Hashing",
      "message": "Password stored in plaintext",
      "severity": "error",
      "suggestion": "Hash password with bcrypt before storage"
    }
  ],
  "warnings": [...],
  "relevant_standards": [...]
}
```

**How it works:**
1. Searches KB for relevant standards based on `action_type`
2. Sends standards + context to LLM for analysis
3. Returns structured violations with fix suggestions
4. Falls back to heuristic matching if LLM unavailable

**Action types:** `create_endpoint`, `add_dependency`, `database_migration`, `auth_change`, `file_upload`, `external_api`

### Code Review

```python
robofleet_review_code(
    code="def handle(...):",
    file_path="src/api/auth.py",
    change_type="modify",  # add, modify, delete
)
```

**Returns:** Score (0-100), comments by severity, approval status
