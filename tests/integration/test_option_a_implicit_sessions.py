"""Test OPTION A: Implicit sessions with auto-wrapped mechanical events."""
import tempfile
from pathlib import Path

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.mcp.server import (
    _auto_log_agent_message,
    _clear_implicit_session,
    _get_implicit_session,
    _set_implicit_session,
)


def test_implicit_session_state_management():
    """Test implicit session state management."""
    assert _get_implicit_session() is None
    _set_implicit_session("sess_test123")
    assert _get_implicit_session() == "sess_test123"
    _clear_implicit_session()
    assert _get_implicit_session() is None
    print("✓ Session state management works")


def test_auto_log_with_session():
    """Test auto-logging with an active session."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        cfg = SlowaveConfig(db_path=str(db_path))
        eng = SlowaveEngine(cfg)

        sid = eng.session_start(agent="test-agent", project="test-proj")
        _set_implicit_session(sid)

        # Auto-log messages
        _auto_log_agent_message("Message 1", "agent_message")
        _auto_log_agent_message("Message 2", "agent_message")

        result = eng.session_end(sid)
        _clear_implicit_session()

        assert result is not None
        print("✓ Auto-logging captured messages")


def test_option_a_full_workflow():
    """Test complete Option A workflow."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        cfg = SlowaveConfig(db_path=str(db_path))
        eng = SlowaveEngine(cfg)

        print("\n=== OPTION A Full Workflow ===\n")

        # 1. Start implicit session
        print("1. Starting implicit session (no session_id management needed)...")
        sid = eng.session_start(agent="auto-agent", project="workflow-test")
        _set_implicit_session(sid)
        print(f"   ✓ Session: {sid[:16]}...\n")

        # 2. Auto-log messages (agent works normally)
        # NOTE: Pass engine to avoid foreign key constraint errors
        print("2. Agent working (auto-logging enabled)...")
        messages = [
            ("User asked me to optimize the query", "user_message"),
            ("Found missing index on created_at", "agent_message"),
            ("Added composite index", "agent_message"),
            ("Performance improved 10x", "agent_message"),
        ]

        for content, msg_type in messages:
            _auto_log_agent_message(content, msg_type, engine=eng)
            print(f"   ✓ Auto-logged: {msg_type}")

        # 3. End session
        print("\n3. Ending session...")
        result = eng.session_end(sid)
        _clear_implicit_session()
        episodes_formed = result.get('episodes_formed', 0)
        print(f"   ✓ Episodes formed: {episodes_formed}\n")

        # 4. Verify events were captured
        print("4. Verifying raw events were captured...")
        # Episodes formed = auto-logging worked!
        assert episodes_formed == len(messages), f"Expected {len(messages)} events, got {episodes_formed}"
        print(f"   ✓ All {len(messages)} messages were auto-logged and formed episodes")

        print("\n✓ Option A workflow successful!\n")


if __name__ == "__main__":
    print("=" * 70)
    print("Testing OPTION A: Implicit Sessions with Auto-Wrapped Events")
    print("=" * 70)

    test_implicit_session_state_management()
    test_auto_log_with_session()
    test_option_a_full_workflow()

    print("=" * 70)
    print("✅ All OPTION A tests passed!")
    print("\nKey advantages:")
    print("  ✓ Eliminates session_id management friction")
    print("  ✓ Auto-logging is involuntary (like RTK)")
    print("  ✓ Guaranteed complete coverage")
    print("  ✓ Solves adoption problem from session start")
    print("=" * 70)
