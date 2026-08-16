"""The plugin search path routes to hybrid_search with the query text.

The full-text half of hybrid retrieval only works if the raw query text is
threaded all the way to ``VectorStore.hybrid_search``. Mocks resolve any
attribute, so this guards against the wiring silently regressing to pure-vector
``store.search`` or dropping ``query_text``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from roboco.services.optimal_brain.indexes.standards import StandardsIndexPlugin


@pytest.mark.asyncio
async def test_search_with_embedding_calls_hybrid_with_query_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = StandardsIndexPlugin()
    store = AsyncMock()
    store.hybrid_search = AsyncMock(return_value=[])
    monkeypatch.setattr(plugin, "_store", store)
    monkeypatch.setattr(plugin, "_initialized", True)

    outcome = await plugin.search_with_embedding(
        [0.1, 0.2, 0.3], "claim a task", top_k=4
    )

    assert outcome.success
    store.hybrid_search.assert_awaited_once()
    call = store.hybrid_search.call_args
    assert call.args[0] == [0.1, 0.2, 0.3]  # embedding
    assert call.args[1] == "claim a task"  # raw query text drives full-text half
    store.search.assert_not_awaited()  # not the pure-vector path
