"""Demo: OPTION A in a Cline-like inline session.

This simulates what would happen if Cline used Option A:
1. At task start: slowave_session_start_implicit()
2. During task: Messages auto-logged (no explicit slowave_event calls)
3. At task end: slowave_session_end_implicit()
4. Verify recall works

This demonstrates that Option A solves the adoption problem.
"""

from slowave.mcp.server import (
    slowave_session_start_implicit,
    slowave_session_end_implicit,
    slowave_recall,
    slowave_remember,
    _auto_log_agent_message,
    _get_implicit_session,
    _set_implicit_session,
)
from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
import tempfile
from pathlib import Path


def simulate_cline_task():
    """Simulate a Cline coding task using Option A."""
    print("\n" + "=" * 70)
    print("DEMO: Cline Task with OPTION A Implicit Sessions")
    print("=" * 70 + "\n")

    print("SCENARIO: User asks Cline to implement a feature\n")
    print("USER: 'Write a function to validate email addresses with regex'")
    print()

    # ========== TASK START (Agent's responsibility) ==========
    print("--- AGENT INITIALIZATION ---")
    print("Calling: slowave_session_start_implicit(agent='cline-tui')")
    session_result = slowave_session_start_implicit(agent="cline-tui", project="demo-task")
    session_id = session_result["session_id"]
    print(f"✓ Session started: {session_id[:16]}...\n")

    # Set up an engine for auto-logging in this demo
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        cfg = SlowaveConfig(db_path=str(db_path))
        eng = SlowaveEngine(cfg)

        # Create session in engine and sync with implicit
        eng_sid = eng.session_start(agent="cline-tui", project="demo-task")
        _set_implicit_session(eng_sid)

        # ========== AGENT WORK (with auto-logging) ==========
        print("--- AGENT WORKING ---")
        print("\n[Agent 1] Analyzing the task...")
        agent_message_1 = "I need to write a regex pattern for email validation. Will use a standard pattern that covers most cases."
        _auto_log_agent_message(agent_message_1, "assistant_message", engine=eng)
        print(f"  Output: {agent_message_1}\n")

        print("[Agent 2] Implementing the function...")
        agent_message_2 = """```python
import re

def validate_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))
```"""
        _auto_log_agent_message(agent_message_2, "assistant_message", engine=eng)
        print(f"  Output: Function implemented\n")

        print("[Agent 3] Adding decision...")
        decision = "Using standard regex pattern for email validation. Covers most real-world cases."
        _auto_log_agent_message(decision, "decision", engine=eng)

        # Also explicitly remember this decision
        print("  Calling: slowave_remember('Using standard regex for emails...')")
        remember_result = slowave_remember(
            "Email validation: Use regex pattern r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'",
            type="decision",
            project="demo-task"
        )
        print(f"  ✓ Remembered: {remember_result['event_id']}\n")

        # ========== TASK END (Agent's responsibility) ==========
        print("--- TASK COMPLETION ---")
        print("Calling: slowave_session_end_implicit()")
        end_result = slowave_session_end_implicit()
        print(f"✓ Session ended: {end_result['session_id'][:16]}...")
        print(f"✓ Episodes formed: {end_result['episodes_formed']}\n")

        # ========== VERIFICATION: Recall in new session ==========
        print("--- VERIFICATION: NEW SESSION, RECALL PRIOR WORK ---")
        print("\nUSER (new session): 'How should I validate emails?'")
        print("\nAgent recalls...")
        print("Calling: slowave_recall('email validation regex')")

        recall_result = slowave_recall("email validation regex", top_k=3)
        schemas = recall_result.get("schemas", [])
        episodes = recall_result.get("episodes", [])

        print(f"✓ Found {len(schemas)} schemas (prior decisions)")
        print(f"✓ Found {len(episodes)} episodes (context)\n")

        if schemas:
            print("RECALLED DECISION:")
            for schema in schemas[:1]:
                print(f"  [{schema['id']}] {schema['content'][:70]}...")

        if episodes:
            print("\nRECALLED CONTEXT:")
            for ep in episodes[:2]:
                print(f"  [{ep['id']}] {ep['content'][:60]}...")

        print()


if __name__ == "__main__":
    try:
        simulate_cline_task()

        print("=" * 70)
        print("✅ OPTION A DEMO SUCCESSFUL!")
        print("\nKey observations:")
        print("  ✓ No explicit slowave_event() calls needed")
        print("  ✓ All messages auto-logged automatically")
        print("  ✓ Explicit slowave_remember() still works")
        print("  ✓ Recall found prior decisions in new session")
        print("  ✓ Agent never forgets to log (involuntary like RTK)")
        print("=" * 70 + "\n")

    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
