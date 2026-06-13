"""Integration test: assert old MCP tool names are absent from the FastMCP registry.

Validates Step 6.6 (hard break — delete old tools).
Old tools deleted: context, session_start, session_end, event, retrieval_feedback, context_feedback
New tools present: activate, remember, recall, reinforce, commit, stats, remember_procedure
"""
from __future__ import annotations


class TestOldToolsDeleted:
    def _get_tool_names(self) -> set[str]:
        """Return the set of registered tool names from the FastMCP instance."""
        import asyncio
        import slowave.mcp.server as srv
        # FastMCP exposes list_tools() as an async method
        loop = asyncio.new_event_loop()
        try:
            tools = loop.run_until_complete(srv.mcp.list_tools())
        finally:
            loop.close()
        return {t.name for t in tools}

    def test_old_tools_absent(self) -> None:
        tool_names = self._get_tool_names()
        deleted = {"context", "session_start", "session_end", "event", "retrieval_feedback", "context_feedback"}
        present_old = deleted & tool_names
        assert not present_old, f"Old tools still registered: {present_old}"

    def test_new_tools_present(self) -> None:
        tool_names = self._get_tool_names()
        expected = {"activate", "remember", "recall", "reinforce", "commit", "stats", "remember_procedure"}
        missing = expected - tool_names
        assert not missing, f"New tools missing from registry: {missing}"
