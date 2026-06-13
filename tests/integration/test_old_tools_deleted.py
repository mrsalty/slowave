"""Integration test: assert old MCP tool names are absent from the FastMCP registry.

Validates Step 6.6 (hard break — delete old tools).
Old / bare names forbidden: context, session_start, session_end, event, retrieval_feedback,
  context_feedback, activate, remember, recall, reinforce, commit, stats, remember_procedure
  (bare names without the slowave_ prefix are not presented correctly to Cline TUI)
New tools present: slowave_activate, slowave_remember, slowave_recall, slowave_reinforce,
                   slowave_commit, slowave_stats, slowave_remember_procedure
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

    def test_bare_names_absent(self) -> None:
        """Bare names (without slowave_ prefix) must not be registered.

        Cline TUI presents tool names to the LLM exactly as registered on the
        server.  If a tool is registered as 'activate', the LLM sees 'activate'
        in the system prompt and is forced to call it as 'activate'.  The
        lifecycle block in .clinerules instructs the LLM to call 'slowave_activate',
        so the names MUST match — bare names guarantee a mismatch and broken tools.
        """
        tool_names = self._get_tool_names()
        bare = {"activate", "remember", "recall", "reinforce", "commit", "stats", "remember_procedure"}
        present_bare = bare & tool_names
        assert not present_bare, (
            f"Bare tool names registered (must use slowave_ prefix): {present_bare}"
        )

    def test_new_tools_present(self) -> None:
        tool_names = self._get_tool_names()
        expected = {"slowave_activate", "slowave_remember", "slowave_recall", "slowave_reinforce", "slowave_commit", "slowave_stats", "slowave_remember_procedure"}
        missing = expected - tool_names
        assert not missing, f"New tools missing from registry: {missing}"
