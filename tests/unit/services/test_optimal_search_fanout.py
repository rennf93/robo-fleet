"""OptimalService.search embeds the query once and fans out across indexes.

Guards the latency fix: previously each index re-ran HyDE + embed sequentially
(N LLM calls, serial), so an all-index search took ~28s. Now the query is
embedded once and every index's vector search runs concurrently with that single
embedding.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from roboco.models.optimal import IndexType, SearchOutcome
from roboco.services.optimal import OptimalService


def _fake_plugin(index_type: IndexType) -> MagicMock:
    plugin = MagicMock()
    plugin.compute_query_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
    plugin.search_with_embedding = AsyncMock(
        return_value=SearchOutcome(results=[], success=True, index_type=index_type)
    )
    plugin.count = AsyncMock(return_value=1)
    return plugin


@pytest.mark.asyncio
async def test_search_embeds_once_and_fans_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = OptimalService.__new__(OptimalService)
    p_docs = _fake_plugin(IndexType.DOCUMENTATION)
    p_journals = _fake_plugin(IndexType.JOURNALS)
    monkeypatch.setattr(svc, "_initialized", True, raising=False)
    monkeypatch.setattr(
        svc,
        "_plugins",
        {IndexType.DOCUMENTATION: p_docs, IndexType.JOURNALS: p_journals},
        raising=False,
    )

    await svc.search("anything")

    # Embedded exactly once total (on the first plugin), reused across indexes —
    # not once per index.
    embed_calls = (
        p_docs.compute_query_embedding.await_count
        + p_journals.compute_query_embedding.await_count
    )
    assert embed_calls == 1
    # Every index ran a vector search with the pre-computed embedding.
    p_docs.search_with_embedding.assert_awaited_once()
    p_journals.search_with_embedding.assert_awaited_once()
