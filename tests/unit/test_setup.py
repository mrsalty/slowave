"""Tests for slowave setup/cleanup core logic.

Uses a fake home directory (tmp_path) so no real config files are touched.
All tests are offline — no binaries, no subprocesses, no network.

Coverage:
  - _patch_mcp_servers          idempotence, new, legacy-upgrade
  - _remove_mcp_servers_from_settings
  - _patch_claude_code_hooks    idempotence, new
  - _inject_block               new file, idempotent update, legacy strip
  - _write_json / _backup_file  backup creation
  - malformed JSON              (SystemExit)
  - _read_json                  missing file returns {}
  - cleanup helpers             _remove_lifecycle_blocks, _remove_mcp_entry
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from slowave.cli.setup import (
    _backup_file,
    _inject_block,
    _patch_claude_code_hooks,
    _patch_mcp_servers,
    _read_json,
    _remove_mcp_servers_from_settings,
    _write_json,
    _MARKER_START,
    _lifecycle_block,
)

MCP_PATH = "/usr/local/bin/slowave-mcp"


# ===========================================================================
# _patch_mcp_servers
# ===========================================================================

class TestPatchMcpServers:
    def test_adds_server_to_empty_config(self):
        cfg, changed = _patch_mcp_servers({}, MCP_PATH)
        assert changed is True
        assert cfg["mcpServers"]["slowave"]["command"] == MCP_PATH

    def test_idempotent_new_format(self):
        cfg = {"mcpServers": {"slowave": {"type": "stdio", "command": MCP_PATH}}}
        _, changed = _patch_mcp_servers(cfg, MCP_PATH)
        assert changed is False

    def test_upgrades_legacy_command_only_format(self):
        cfg = {"mcpServers": {"slowave": {"command": MCP_PATH}}}
        cfg2, changed = _patch_mcp_servers(cfg, MCP_PATH)
        assert changed is True
        assert cfg2["mcpServers"]["slowave"]["type"] == "stdio"

    def test_replaces_stale_path(self):
        cfg = {"mcpServers": {"slowave": {"type": "stdio", "command": "/old/path/slowave-mcp"}}}
        _, changed = _patch_mcp_servers(cfg, MCP_PATH)
        assert changed is True

    def test_preserves_other_mcp_servers(self):
        cfg = {"mcpServers": {"othertool": {"command": "/usr/bin/other"}}}
        cfg2, _ = _patch_mcp_servers(cfg, MCP_PATH)
        assert "othertool" in cfg2["mcpServers"]


# ===========================================================================
# _remove_mcp_servers_from_settings
# ===========================================================================

class TestRemoveMcpServersFromSettings:
    def test_removes_slowave_entry(self):
        cfg = {"mcpServers": {"slowave": {"command": MCP_PATH}}}
        cfg2, changed = _remove_mcp_servers_from_settings(cfg)
        assert changed is True
        assert "slowave" not in cfg2.get("mcpServers", {})

    def test_removes_empty_mcpServers_key(self):
        cfg = {"mcpServers": {"slowave": {"command": MCP_PATH}}}
        cfg2, _ = _remove_mcp_servers_from_settings(cfg)
        assert "mcpServers" not in cfg2

    def test_no_change_when_absent(self):
        _, changed = _remove_mcp_servers_from_settings({"otherKey": "value"})
        assert changed is False

    def test_no_change_when_slowave_not_present(self):
        _, changed = _remove_mcp_servers_from_settings({"mcpServers": {"othertool": {}}})
        assert changed is False

    def test_preserves_other_servers(self):
        cfg = {"mcpServers": {"slowave": {}, "other": {"command": "/x"}}}
        cfg2, changed = _remove_mcp_servers_from_settings(cfg)
        assert changed is True
        assert "other" in cfg2["mcpServers"]


# ===========================================================================
# _patch_claude_code_hooks
# ===========================================================================

class TestPatchClaudeCodeHooks:
    def test_adds_hooks_to_empty_config(self):
        cfg, changed = _patch_claude_code_hooks({})
        assert changed is True
        assert "UserPromptSubmit" in cfg["hooks"]
        assert "Stop" in cfg["hooks"]

    def test_idempotent_when_hooks_present(self):
        cfg, _ = _patch_claude_code_hooks({})
        _, changed2 = _patch_claude_code_hooks(cfg)
        assert changed2 is False

    def test_preserves_unrelated_hooks(self):
        existing = {"hooks": {"PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "echo hi"}]}]}}
        cfg2, _ = _patch_claude_code_hooks(existing)
        assert "PreToolUse" in cfg2["hooks"]

    def test_replaces_stale_hook_command(self):
        """If hook is present but command text differs (version upgrade), it is replaced."""
        stale_cmd = "echo 'SLOWAVE MANDATORY: old instructions'"
        cfg = {"hooks": {"UserPromptSubmit": [{"matcher": "", "hooks": [{"type": "command", "command": stale_cmd}]}]}}
        cfg2, changed = _patch_claude_code_hooks(cfg)
        assert changed is True
        # Stale command should be gone
        cmds = [h["command"] for g in cfg2["hooks"]["UserPromptSubmit"] for h in g.get("hooks", [])]
        assert stale_cmd not in cmds
        # Current command should be present
        from slowave.cli.setup import _USER_PROMPT_CMD
        assert any(_USER_PROMPT_CMD in c for c in cmds)

    def test_idempotent_with_current_hook_command(self):
        """If hook already has the exact current command, no change."""
        from slowave.cli.setup import _USER_PROMPT_CMD, _STOP_CMD
        cfg = {
            "hooks": {
                "UserPromptSubmit": [{"matcher": "", "hooks": [{"type": "command", "command": _USER_PROMPT_CMD}]}],
                "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": _STOP_CMD}]}],
            }
        }
        _, changed = _patch_claude_code_hooks(cfg)
        assert changed is False


# ===========================================================================
# _inject_block
# ===========================================================================

class TestInjectBlock:
    def test_creates_new_file(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        changed = _inject_block(target, _lifecycle_block("claude-code"))
        assert changed is True
        assert target.exists()
        assert _MARKER_START in target.read_text()

    def test_idempotent_on_second_call(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        block = _lifecycle_block("claude-code")
        _inject_block(target, block)
        changed = _inject_block(target, block)
        assert changed is False

    def test_updates_stale_v1_block(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        old = "<!-- slowave-lifecycle-start v1 -->\nold content\n<!-- slowave-lifecycle-end v1 -->\n"
        target.write_text(old, encoding="utf-8")
        changed = _inject_block(target, _lifecycle_block("claude-code"))
        assert changed is True
        content = target.read_text()
        assert "old content" not in content
        assert _MARKER_START in content

    def test_prepends_before_existing_user_content(self, tmp_path):
        target = tmp_path / ".clinerules"
        target.write_text("# My existing rules\n", encoding="utf-8")
        _inject_block(target, _lifecycle_block("cline-tui"))
        content = target.read_text()
        assert content.index(_MARKER_START) < content.index("# My existing rules")

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "CLAUDE.md"
        _inject_block(target, _lifecycle_block("claude-code"))
        assert target.exists()

    def test_strips_legacy_unmarked_section(self, tmp_path):
        # Legacy section ends when the next same-level (##) heading is found.
        legacy = "## Slowave memory\nsome old content\n\n## My Notes\nuser content\n"
        target = tmp_path / "CLAUDE.md"
        target.write_text(legacy, encoding="utf-8")
        _inject_block(target, _lifecycle_block("claude-code"))
        content = target.read_text()
        assert "some old content" not in content
        assert "## My Notes" in content
        assert "user content" in content


# ===========================================================================
# _write_json + _backup_file
# ===========================================================================

class TestWriteJsonBackup:
    def test_backup_created_before_overwrite(self, tmp_path):
        target = tmp_path / "config.json"
        target.write_text('{"original": true}\n', encoding="utf-8")
        _write_json(target, {"updated": True})
        backups = list(tmp_path.glob("config.json.bak.*"))
        assert len(backups) == 1
        assert json.loads(backups[0].read_text()) == {"original": True}

    def test_no_backup_when_file_missing(self, tmp_path):
        _write_json(tmp_path / "new.json", {"key": "val"})
        assert list(tmp_path.glob("new.json.bak.*")) == []

    def test_write_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "a" / "b" / "cfg.json"
        _write_json(target, {"x": 1})
        assert target.exists()
        assert json.loads(target.read_text()) == {"x": 1}

    def test_backup_file_direct(self, tmp_path):
        f = tmp_path / "myfile.txt"
        f.write_text("hello", encoding="utf-8")
        bak = _backup_file(f)
        assert bak is not None and bak.exists()
        assert bak.read_text() == "hello"
        assert ".bak." in bak.name

    def test_backup_file_returns_none_when_missing(self, tmp_path):
        assert _backup_file(tmp_path / "nonexistent.txt") is None

    def test_only_one_backup_kept_on_multiple_writes(self, tmp_path):
        """Re-running setup must not accumulate backup copies."""
        target = tmp_path / "config.json"
        target.write_text('{"v": 1}\n', encoding="utf-8")
        _write_json(target, {"v": 2})
        _write_json(target, {"v": 3})
        backups = list(tmp_path.glob("config.json.bak.*"))
        assert len(backups) == 1
        # The surviving backup is from the second write (before v3 was written)
        assert json.loads(backups[0].read_text()) == {"v": 2}


class TestInjectBlockBackup:
    def test_backup_on_update(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        original = "<!-- slowave-lifecycle-start v1 -->\nold\n<!-- slowave-lifecycle-end v1 -->\n"
        target.write_text(original, encoding="utf-8")
        _inject_block(target, _lifecycle_block("claude-code"))
        backups = list(tmp_path.glob("CLAUDE.md.bak.*"))
        assert len(backups) == 1
        assert backups[0].read_text() == original

    def test_backup_when_prepending_to_existing(self, tmp_path):
        target = tmp_path / ".clinerules"
        target.write_text("# existing\n", encoding="utf-8")
        _inject_block(target, _lifecycle_block("cline-tui"))
        assert len(list(tmp_path.glob(".clinerules.bak.*"))) == 1

    def test_no_backup_for_brand_new_file(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        _inject_block(target, _lifecycle_block("claude-code"))
        assert list(tmp_path.glob("CLAUDE.md.bak.*")) == []


# ===========================================================================
# _read_json
# ===========================================================================

class TestReadJson:
    def test_returns_empty_dict_for_missing_file(self, tmp_path):
        assert _read_json(tmp_path / "nonexistent.json") == {}

    def test_reads_valid_json(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        assert _read_json(f) == {"key": "value"}

    def test_exits_on_malformed_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(SystemExit):
            _read_json(f)


# ===========================================================================
# Cleanup helpers — _remove_lifecycle_blocks, _remove_mcp_configs
# Monkey-patches _home() in both modules to redirect to tmp_path.
# ===========================================================================

import slowave.cli.cleanup as _cleanup_mod
import slowave.cli.setup as _setup_mod


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    """Redirect _home() to tmp_path in both setup and cleanup modules."""
    monkeypatch.setattr(_setup_mod, "_home", lambda: tmp_path)
    monkeypatch.setattr(_cleanup_mod, "_home", lambda: tmp_path)
    return tmp_path


class TestCleanupRemoveLifecycleBlocks:
    def test_removes_block_from_clinerules(self, fake_home):
        target = fake_home / ".clinerules"
        block = _lifecycle_block("cline-tui")
        target.write_text(block + "\n# My Notes\n", encoding="utf-8")

        count = _cleanup_mod._remove_lifecycle_blocks(dry_run=False)

        assert count >= 1
        remaining = target.read_text()
        assert _MARKER_START not in remaining
        assert "# My Notes" in remaining

    def test_removes_block_from_claude_md(self, fake_home):
        claude_dir = fake_home / ".claude"
        claude_dir.mkdir(parents=True)
        target = claude_dir / "CLAUDE.md"
        block = _lifecycle_block("claude-code")
        target.write_text(block, encoding="utf-8")

        count = _cleanup_mod._remove_lifecycle_blocks(dry_run=False)

        assert count >= 1
        # File with only the block becomes empty → unlinked
        assert not target.exists() or _MARKER_START not in target.read_text()

    def test_dry_run_does_not_modify_files(self, fake_home):
        target = fake_home / ".clinerules"
        block = _lifecycle_block("cline-tui")
        original = block + "\n# Notes\n"
        target.write_text(original, encoding="utf-8")

        _cleanup_mod._remove_lifecycle_blocks(dry_run=True)

        assert target.read_text() == original

    def test_no_op_on_file_without_slowave_content(self, fake_home):
        target = fake_home / ".clinerules"
        target.write_text("# Regular rules\n", encoding="utf-8")

        count = _cleanup_mod._remove_lifecycle_blocks(dry_run=False)

        assert count == 0
        assert target.read_text() == "# Regular rules\n"


class TestCleanupRemoveMcpConfigs:
    def test_removes_slowave_from_cursor_mcp(self, fake_home):
        cursor_dir = fake_home / ".cursor"
        cursor_dir.mkdir()
        cfg_path = cursor_dir / "mcp.json"
        cfg_path.write_text(
            json.dumps({"mcpServers": {"slowave": {"command": MCP_PATH}, "other": {}}}),
            encoding="utf-8",
        )

        count = _cleanup_mod._remove_mcp_configs(dry_run=False)

        assert count >= 1
        remaining = json.loads(cfg_path.read_text())
        assert "slowave" not in remaining.get("mcpServers", {})
        assert "other" in remaining["mcpServers"]

    def test_dry_run_does_not_write_mcp_configs(self, fake_home):
        cursor_dir = fake_home / ".cursor"
        cursor_dir.mkdir()
        cfg_path = cursor_dir / "mcp.json"
        original = json.dumps({"mcpServers": {"slowave": {"command": MCP_PATH}}})
        cfg_path.write_text(original, encoding="utf-8")

        _cleanup_mod._remove_mcp_configs(dry_run=True)

        assert cfg_path.read_text() == original

    def test_no_op_when_no_mcp_files_exist(self, fake_home):
        count = _cleanup_mod._remove_mcp_configs(dry_run=False)
        assert count == 0


class TestCleanupRemoveSetupBackups:
    def test_removes_bak_files_from_home(self, fake_home):
        bak = fake_home / ".clinerules.bak.20260611_120000"
        bak.write_text("old content", encoding="utf-8")

        count = _cleanup_mod._remove_setup_backups(dry_run=False)

        assert count == 1
        assert not bak.exists()

    def test_removes_bak_files_from_claude_dir(self, fake_home):
        (fake_home / ".claude").mkdir()
        bak = fake_home / ".claude" / "settings.json.bak.20260611_120000"
        bak.write_text("{}", encoding="utf-8")

        count = _cleanup_mod._remove_setup_backups(dry_run=False)

        assert count == 1
        assert not bak.exists()

    def test_dry_run_does_not_delete_backups(self, fake_home):
        bak = fake_home / ".clinerules.bak.20260611_120000"
        bak.write_text("old content", encoding="utf-8")

        _cleanup_mod._remove_setup_backups(dry_run=True)

        assert bak.exists()

    def test_no_op_when_no_backups_exist(self, fake_home):
        count = _cleanup_mod._remove_setup_backups(dry_run=False)
        assert count == 0
