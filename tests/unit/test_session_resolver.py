"""Test: per-scope implicit session resolver with 1h age guard.

Tests verify:
1. bind() → resolve() returns the bound id
2. resolve() on unknown scope returns None
3. After backdating an entry past TTL, resolve() returns None and removes it
4. clear() removes the binding
5. Two scopes are isolated
"""

import time

from slowave.mcp.session_resolver import SessionResolver


def test_bind_resolve():
    """bind() → resolve() returns the bound id."""
    resolver = SessionResolver()
    resolver.bind("project:test", "sess_abc123")

    result = resolver.resolve("project:test")
    assert result == "sess_abc123", f"Expected 'sess_abc123', got {result}"


def test_resolve_unknown_scope():
    """resolve() on unknown scope returns None."""
    resolver = SessionResolver()

    result = resolver.resolve("project:unknown")
    assert result is None, f"Expected None, got {result}"


def test_resolve_stale_binding():
    """After backdating an entry past TTL, resolve() returns None and removes it."""
    resolver = SessionResolver(max_age_s=10)  # Very short TTL for testing

    # Bind a session
    resolver.bind("project:test", "sess_old")

    # Manually backdate the binding to be older than TTL
    now_ts = int(time.time())
    bindings = resolver._bindings()
    binding = bindings["project:test"]
    binding.set_at_ts = now_ts - 15  # 15 seconds ago (past 10s TTL)

    # Resolve should return None and remove the binding
    result = resolver.resolve("project:test")
    assert result is None, f"Expected None for stale binding, got {result}"

    # Verify binding was removed
    assert "project:test" not in bindings, "Stale binding should be removed"


def test_clear():
    """clear() removes the binding."""
    resolver = SessionResolver()
    resolver.bind("project:test", "sess_123")

    # Verify it exists
    assert resolver.resolve("project:test") == "sess_123"

    # Clear it
    resolver.clear("project:test")

    # Verify it's gone
    assert resolver.resolve("project:test") is None, "Binding should be cleared"


def test_scope_isolation():
    """Two scopes are isolated."""
    resolver = SessionResolver()

    resolver.bind("project:alpha", "sess_alpha")
    resolver.bind("project:beta", "sess_beta")
    resolver.bind(None, "sess_none")

    assert resolver.resolve("project:alpha") == "sess_alpha"
    assert resolver.resolve("project:beta") == "sess_beta"
    assert resolver.resolve(None) == "sess_none"

    # Clearing one scope doesn't affect others
    resolver.clear("project:alpha")
    assert resolver.resolve("project:alpha") is None
    assert resolver.resolve("project:beta") == "sess_beta"
    assert resolver.resolve(None) == "sess_none"


def test_snapshot():
    """snapshot() returns all current bindings with metadata."""
    resolver = SessionResolver(max_age_s=100)
    resolver.bind("project:test", "sess_123")
    resolver.bind(None, "sess_default")

    snap = resolver.snapshot()
    assert "project:test" in snap
    assert snap["project:test"]["session_id"] == "sess_123"
    assert snap["project:test"]["fresh"] is True
    assert snap["project:test"]["age_s"] >= 0

    assert None in snap
    assert snap[None]["session_id"] == "sess_default"


def test_scope_rebinding():
    """Binding a new session_id to the same scope replaces the old one."""
    resolver = SessionResolver()
    resolver.bind("project:test", "sess_old")
    assert resolver.resolve("project:test") == "sess_old"

    # Rebind
    resolver.bind("project:test", "sess_new")
    assert resolver.resolve("project:test") == "sess_new"


def test_thread_isolation():
    """Two threads with the same scope are isolated — no collision."""
    import threading

    resolver = SessionResolver()
    results = {}

    def thread_a():
        resolver.bind("project:shared", "sess_a")
        results["a"] = resolver.resolve("project:shared")

    def thread_b():
        resolver.bind("project:shared", "sess_b")
        results["b"] = resolver.resolve("project:shared")

    ta = threading.Thread(target=thread_a)
    tb = threading.Thread(target=thread_b)
    ta.start()
    tb.start()
    ta.join()
    tb.join()

    assert results["a"] == "sess_a"
    assert results["b"] == "sess_b"


if __name__ == "__main__":
    test_bind_resolve()
    test_resolve_unknown_scope()
    test_resolve_stale_binding()
    test_clear()
    test_scope_isolation()
    test_snapshot()
    test_scope_rebinding()
    test_thread_isolation()
    print("All tests passed!")
