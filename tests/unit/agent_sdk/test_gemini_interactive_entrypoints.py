"""Gemini/ADK interactive entrypoints wire the right MCP server module.

The ``gemini_intake_main`` / ``gemini_secretary_main`` modules are thin: they
compose ``GeminiChatSession`` (which builds an ADK ``McpToolset`` for the role's
MCP server) with the shared transport. The testable surface is that the modules
import cleanly and the session factory references the right ``server_module``
(intake_server vs secretary_server) - the one structural choice that determines
which MCP tools the agent gets.
"""

from __future__ import annotations

import inspect

from robofleet.agent_sdk import gemini_intake_main, gemini_secretary_main
from robofleet.agent_sdk.gemini_chat_session import GeminiChatSession


def test_gemini_intake_main_imports_session_and_transport() -> None:
    """The intake main must compose GeminiChatSession with the shared transport."""
    assert hasattr(gemini_intake_main, "main")
    assert hasattr(gemini_intake_main, "GeminiChatSession")
    # The shared transport helpers are imported (not re-defined locally).
    assert hasattr(gemini_intake_main, "build_receiver")
    assert hasattr(gemini_intake_main, "make_message_source")
    assert hasattr(gemini_intake_main, "make_relay_sink")
    assert hasattr(gemini_intake_main, "IntakeDriver")


def test_gemini_secretary_main_imports_session_and_transport() -> None:
    """The secretary main must compose GeminiChatSession with the shared transport."""
    assert hasattr(gemini_secretary_main, "main")
    assert hasattr(gemini_secretary_main, "GeminiChatSession")
    assert hasattr(gemini_secretary_main, "build_receiver")
    assert hasattr(gemini_secretary_main, "make_message_source")
    assert hasattr(gemini_secretary_main, "make_relay_sink")
    assert hasattr(gemini_secretary_main, "IntakeDriver")


def test_gemini_chat_session_server_module_is_set_at_factory_call() -> None:
    """GeminiChatSession takes server_module as a constructor arg - the intake
    main's session_factory must pass 'intake_server' and the secretary main's
    must pass 'secretary_server'. We verify the constructor signature accepts it
    and the source code of each main references the right module name."""
    sig = inspect.signature(GeminiChatSession.__init__)
    assert "server_module" in sig.parameters
    assert "system_prompt" in sig.parameters

    intake_src = inspect.getsource(gemini_intake_main)
    assert "intake_server" in intake_src
    assert "secretary_server" not in intake_src

    sec_src = inspect.getsource(gemini_secretary_main)
    assert "secretary_server" in sec_src
    assert "intake_server" not in sec_src


def test_gemini_chat_session_relay_kind_matches_role() -> None:
    """The intake main uses the default relay kind ('prompter'); the secretary
    main passes kind='secretary' to make_relay_sink."""
    intake_src = inspect.getsource(gemini_intake_main)
    # Default kind is 'prompter' - no explicit kind= needed.
    assert "make_relay_sink" in intake_src

    sec_src = inspect.getsource(gemini_secretary_main)
    assert 'kind="secretary"' in sec_src or "kind='secretary'" in sec_src
