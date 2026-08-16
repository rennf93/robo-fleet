# Knowledge Base Troubleshooting

## Empty Search Results

**Problem**: `robofleet_kb_search()` returns nothing

**Causes**:
1. Content not indexed yet
2. Query too specific
3. Wrong index type filter

**Solutions**:
- Check what's indexed: `robofleet_kb_stats()`
- Broaden query terms
- Remove index_types filter
- Trigger reindex: `robofleet_reindex_all()`

## Empty RAG Response

**Problem**: `robofleet_rag_query()` returns empty answer

**Causes**:
1. No relevant context found
2. LLM returned thinking tags only
3. Query too vague

**Solutions**:
- Check KB has relevant content
- Rephrase query to be more specific
- Use `robofleet_kb_search()` first to verify content exists

## Mentor Not Responding

**Problem**: `robofleet_ask_mentor()` fails or empty

**Causes**:
1. LLM timeout
2. No relevant KB content
3. Service temporarily unavailable

**Solutions**:
- Retry the query
- Check KB stats
- Use `robofleet_kb_search()` as fallback

## Index Failed

**Problem**: `robofleet_kb_index_code()` or `robofleet_kb_index_docs()` fails

**Causes**:
1. Invalid file patterns
2. Files not accessible
3. Embedding service down

**Solutions**:
- Verify file patterns match files
- Check file permissions
- Verify Ollama is running

## Documentation Write Failed

**Problem**: `robofleet_docs_write()` fails

**Causes**:
1. Invalid doc_type (must be: api, qa, guide, readme, changelog, architecture, design)
2. Missing required fields (task_id, filename, title, content)
3. Agent not authorized (only documenter and cell_pm roles)
4. Task not found

**Solutions**:
- Verify doc_type is valid
- Ensure all required fields provided
- Check your role has write permission
- Verify task_id exists

## Duplicate Documentation Created

**Problem**: Created duplicate docs instead of updating existing

**Causes**:
1. Content too different from existing doc (RAG similarity < 0.75)
2. Doc in different team folder
3. RAG search failed (but write still succeeded)

**Solutions**:
- Ensure content covers same topic as existing doc
- Check existing docs first: `robofleet_docs_list(task_id)`
- Search KB: `robofleet_kb_search("topic keywords")`
- Delete duplicate if needed: `robofleet_docs_delete(path)`

**Note**: `robofleet_docs_write()` uses RAG to auto-deduplicate by **content similarity** (not just title). If content is semantically similar (>75% similarity), it updates instead of creating new.

## Cannot Clear Index

**Problem**: "Not authorized to clear index"

**Cause**: Only PM/CEO can clear indexes

**Solution**: Ask PM or CEO to clear if needed

## Proactive Context Empty

**Problem**: `robofleet_get_proactive_context()` returns empty

**Cause**: No relevant context found for task

**Solution**: Manual search with `robofleet_kb_search()` using task keywords
