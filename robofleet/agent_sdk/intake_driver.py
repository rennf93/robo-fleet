"""Intake agent driver — the normalized stream chunk + driver loop.

The intake (``prompter``) agent is an interactive session. The runtime-specific
session (Gemini/ADK via ``GeminiChatSession``, grok CLI via ``GrokChatSession``)
lives in its own module; this one holds the SDK-free ``StreamChunk`` shape, the
``IntakeSession`` Protocol, the draft coercion helpers shared by every runtime,
and the ``IntakeDriver`` loop that pulls the human's next message and streams the
agent's reply back to the relay. SDK-free and unit-tested with fakes.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from robofleet.agent_sdk.prompt_guard import detect_injection, refusal_message

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

logger = structlog.get_logger()

# The intake agent emits the finished structured task draft as a fenced block
# (see the prompter system prompt). The driver mines it from the complete reply
# and surfaces it as one ``draft`` chunk for the panel's draft card.
_DRAFT_FENCE = re.compile(r"```robofleet-draft\s*\n(.*?)```", re.DOTALL)


# ---------------------------------------------------------------------------
# Normalized stream chunk — what the panel SSE consumes. SDK-free.
# ---------------------------------------------------------------------------


@dataclass
class StreamChunk:
    """One normalized event in the agent's live reply.

    ``kind`` is the panel-facing event type; the rest is payload. Decoupled
    from the SDK's message classes so the relay/panel never import the SDK.
    """

    kind: str  # text|thinking|tool_use|tool_result|turn_end|system|draft|batch|error
    text: str = ""
    tool: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def _coerce_to_list(value: Any) -> list[Any]:
    """Wrap a lone scalar/dict into a one-element list; drop junk to ``[]``.

    Mirrors ``content.validators.coerce_to_list`` but always returns a list
    (never ``None``) and never passes a non-list, non-scalar/dict through — the
    panel treats these fields as arrays and would crash on anything else. A
    bare string/dict is the well-intentioned single-item case (wrap it); a
    number/bool/None is not a work unit, so it is dropped.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str | dict):
        return [value]
    return []


# Fields that are lists of plain strings (vs ``the_work``, a list of work-unit
# dicts). The agent may emit these as XML-ish ``<item>…</item>`` elements, which
# the SDK parses into ``[{"item": {"$text": "…"}}, …]`` — coerce to flat str
# lists so they reach the panel and a VARCHAR[] column as strings, not dicts.
_STR_LIST_FIELDS = ("acceptance_criteria", "what_this_builds", "notes")


def _coerce_draft(data: Any) -> dict[str, Any] | None:
    """Return ``data`` as a draft dict (with a string ``title``), else ``None``.

    Accepts a dict, or a JSON string the agent may have passed. Coerces the
    list-shaped spec fields: ``the_work`` (a list of work-unit dicts) is wrapped
    to a list, and each ``the_work`` entry's ``items`` plus the string-list
    fields (``acceptance_criteria``, ``what_this_builds``, ``notes``) are
    flattened to ``list[str]`` — the agent sometimes emits these as XML-ish
    ``<item>…</item>`` elements that the SDK parses into dict wrappers, which
    would crash a ``VARCHAR[]`` insert and dump ``str(dict)`` into the rendered
    description. The panel renders ``(draft.the_work ?? []).map(...)`` and
    throws if ``the_work`` is a bare object, so this is the single choke point
    that keeps a non-array from ever reaching SSE.
    """
    from robofleet.foundation.policy.content.validators import coerce_str_list

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            return None
    if not (isinstance(data, dict) and isinstance(data.get("title"), str)):
        return None
    coerced = dict(data)
    _coerce_spec_fields(coerced, coerce_str_list)
    return coerced


def _coerce_spec_fields(
    coerced: dict[str, Any], coerce: Callable[[Any], list[str]]
) -> None:
    """Coerce the list-shaped spec fields in place: wrap the_work, flatten the
    string-list fields, and flatten each the_work unit's items to ``list[str]``."""
    if "the_work" in coerced:
        coerced["the_work"] = _coerce_to_list(coerced["the_work"])
    for key in _STR_LIST_FIELDS:
        if key in coerced:
            coerced[key] = coerce(coerced[key])
    work = coerced.get("the_work")
    if isinstance(work, list):
        coerced["the_work"] = [
            {
                **unit,
                "items": coerce(unit.get("items")),
            }
            for unit in work
            if isinstance(unit, dict)
        ]


def _extract_draft(text: str) -> dict[str, Any] | None:
    """Parse a fenced ``robofleet-draft`` JSON block out of the agent's reply.

    A fallback to the ``propose_draft`` tool: returns the parsed object (a dict
    with a string ``title``) or ``None`` when no well-formed block is present.
    """
    match = _DRAFT_FENCE.search(text)
    if match is None:
        return None
    return _coerce_draft(match.group(1))


# ---------------------------------------------------------------------------
# Session seam — one conversational turn -> a stream of chunks.
# ---------------------------------------------------------------------------


class IntakeSession(Protocol):
    """A live agent session. ``send`` runs one turn and streams its chunks."""

    def send(self, text: str) -> AsyncIterator[StreamChunk]: ...


# A factory that yields an async-context-managed IntakeSession (opens/closes
# the underlying client). Injected so the driver loop is testable with a fake.
SessionFactory = Callable[[], "AbstractAsyncContextManager[IntakeSession]"]
# Source of the human's messages (e.g. the in-container inbox). Returns None to
# signal shutdown (container being reaped).
MessageSource = Callable[[], Awaitable[str | None]]
# Where normalized chunks go (the relay -> panel SSE).
EventSink = Callable[[StreamChunk], Awaitable[None]]


# ---------------------------------------------------------------------------
# The driver loop — SDK-free, unit-tested with fakes.
# ---------------------------------------------------------------------------


class IntakeDriver:
    """Owns the chat loop for the lifetime of one intake session."""

    def __init__(
        self,
        session_factory: SessionFactory,
        next_message: MessageSource,
        emit: EventSink,
    ) -> None:
        self._session_factory = session_factory
        self._next_message = next_message
        self._emit = emit
        self.log = logger.bind(component="intake_driver")

    async def run(self) -> None:
        """Open the session and process human turns until shutdown.

        One ``ClaudeSDKClient`` is held open across all turns (context persists
        in-process). The loop ends when ``next_message`` returns ``None``.
        """
        async with self._session_factory() as session:
            self.log.info("Intake session opened")
            turns = 0
            while True:
                text = await self._next_message()
                if text is None:
                    self.log.info("Intake session closing", turns=turns)
                    return
                turns += 1
                self.log.info("Intake turn received", turn=turns, chars=len(text))
                await self._run_turn(session, text)

    async def _run_turn(self, session: IntakeSession, text: str) -> None:
        """Stream one turn's chunks to the sink, logging each tool call.

        The conversation streams to the relay (panel), not stdout — so without
        this, ``docker logs`` on the intake container is a black box between turn
        start and end even while the agent reads the codebase and spawns subagents.
        Logging each ``tool_use`` (and the draft) shows the turn's real shape;
        text deltas are intentionally NOT logged (they'd spam). A failure ends as
        an error chunk.
        """
        # Prompt-injection guard at the input boundary (our own guard, runtime-
        # agnostic): deny a poisoned turn before the model ever sees it. Covers
        # the Grok (grok-CLI) session and the Claude SDK session — the latter
        # runs with setting_sources=[] and so never loads the bash UserPromptSubmit
        # hook, so this is the only injection guard either interactive path has.
        injection = detect_injection(text)
        if injection is not None:
            self.log.warning("Intake turn denied: prompt-injection", reason=injection)
            await self._emit(StreamChunk(kind="error", text=refusal_message(injection)))
            return

        chunks = 0
        tools = 0
        drafted = False
        try:
            async for chunk in session.send(text):
                chunks += 1
                if chunk.kind == "tool_use":
                    tools += 1
                    self.log.info("Intake tool use", tool=chunk.tool)
                elif chunk.kind == "draft":
                    drafted = True
                    self.log.info("Intake draft emitted")
                elif chunk.kind == "batch":
                    drafted = True
                    self.log.info(
                        "Intake MegaTask batch emitted",
                        items=len(chunk.data.get("drafts", [])),
                    )
                await self._emit(chunk)
        except Exception as exc:
            self.log.error("Intake turn failed", error=str(exc), chunks=chunks)
            await self._emit(StreamChunk(kind="error", text=str(exc)))
        else:
            self.log.info(
                "Intake turn streamed", chunks=chunks, tools=tools, drafted=drafted
            )
