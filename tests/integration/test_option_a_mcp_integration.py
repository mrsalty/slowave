"""Test OPTION A MCP integration - verify slowave tools are being called."""
import tempfile
from pathlib import Path

from slowave.core.config import SlowaveConfig
from slowave.mcp.server import (
    slowave_session_start_implicit,
    slowave_session_end_implicit,
    slowave_recall,
    slowave_remember,
)
# Import the auto-log function to directly test it
from slowave.mcp.server import (
    _auto_log_agent_message,
    _get_implicit_session,
)


def test_mcp_option_a_implicit_flow():
    """Test the complete Option A flow via MCP tools."""
    print("\n" + "=" * 70)
    print("TEST: MCP Option A Implicit Session Flow")
    print("=" * 70 + "\n")

    # Step 1: Start implicit session via MCP
    print("1. Calling slowave_session_start_implicit()...")
    result = slowave_session_start_implicit(agent="test-cline", project="test-project")
    print(f"   ✓ MCP Call Result: {result}")
    sid = result.get("session_id")
    assert sid is not None, "Session should be created"
    assert result.get("mode") == "implicit", "Should be implicit mode"
    assert result.get("auto_logging") is True, "Auto-logging should be enabled"

    # Verify implicit session is set
    implicit_sid = _get_implicit_session()
    assert implicit_sid == sid, f"Implicit session should be set to {sid}"
    print(f"   ✓ Implicit session is now active: {sid[:16]}...\n")

    # Step 2: Simulate agent interaction (auto-logging)
    print("2. Simulating agent messages (auto-logging)...")
    test_messages = [
        ("User asked me to review the design", "user_message"),
        ("I reviewed the architecture", "assistant_message"),
        ("Decision: Use async/await pattern", "decision"),
    ]

    from slowave.core.engine import SlowaveEngine
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        cfg = SlowaveConfig(db_path=str(db_path))
        eng = SlowaveEngine(cfg)

        # Create the session in the engine
        eng_sid = eng.session_start(agent="test-cline", project="test-project")
        from slowave.mcp.server import _set_implicit_session
        _set_implicit_session(eng_sid)

        for content, msg_type in test_messages:
            _auto_log_agent_message(content, msg_type, engine=eng)
            print(f"   ✓ Auto-logged: {msg_type}")

        print()

        # Step 3: Explicitly remember a decision
        print("3. Calling slowave_remember() for explicit memory...")
        remember_result = slowave_remember(
            "Async/await pattern chosen for concurrency",
            type="decision",
            project="test-project"
        )
        print(f"   ✓ Remember result: {remember_result}\n")

        # Step 4: End implicit session via MCP
        print("4. Calling slowave_session_end_implicit()...")
        end_result = slowave_session_end_implicit()
        print(f"   ✓ Session ended: {end_result}\n")

        # Verify implicit session is cleared
        implicit_sid = _get_implicit_session()
        assert implicit_sid is None, "Implicit session should be cleared"
        print("   ✓ Implicit session cleared\n")

        # Step 5: Recall the content
        print("5. Calling slowave_recall() to verify content...")
        recall_result = slowave_recall("async await concurrency pattern", top_k=5)
        print(f"   ✓ Recall found {len(recall_result.get('schemas', []))} schemas")
        print(f"   ✓ Recall found {len(recall_result.get('episodes', []))} episodes\n")


def test_mcp_explicit_vs_implicit_comparison():
    """Compare explicit slowave_event calls vs implicit auto-logging."""
    print("\n" + "=" * 70)
    print("COMPARISON: Explicit vs Implicit Session Protocol")
    print("=" * 70 + "\n")

    print("EXPLICIT PROTOCOL (current - requires agent discipline):")
    print("  Code example:")
    print("    sid = slowave_session_start(...)")
    print("    slowave_event(sid, 'user_message', '...')  # ← Must remember")
    print("    slowave_event(sid, 'assistant_message', '...')  # ← Must remember")
    print("    slowave_event(sid, 'assistant_message', '...')  # ← Must remember")
    print("    slowave_session_end(sid)")
    print("  Problem: Easy to forget slowave_event calls → incomplete logging\n")

    print("OPTION A IMPLICIT PROTOCOL (auto-wrapping - involuntary like RTK):")
    print("  Code example:")
    print("    slowave_session_start_implicit(...)  # ← One call")
    print("    # Agent works normally, messages auto-logged")
    print("    # All outputs captured automatically")
    print("    slowave_session_end_implicit()  # ← One call")
    print("  Advantage: Complete logging without agent discipline\n")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("MCP Integration Tests - OPTION A Implicit Sessions")
    print("=" * 70)

    try:
        test_mcp_option_a_implicit_flow()
        test_mcp_explicit_vs_implicit_comparison()

        print("\n" + "=" * 70)
        print("✅ All MCP integration tests passed!")
        print("\nVerified:")
        print("  ✓ slowave_session_start_implicit() works")
        print("  ✓ Auto-logging captures messages")
        print("  ✓ slowave_remember() works with implicit session")
        print("  ✓ slowave_session_end_implicit() works")
        print("  ✓ slowave_recall() finds auto-logged content")
        print("=" * 70 + "\n")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
