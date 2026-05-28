# Claude Desktop + Slowave

Goal: configure Claude Desktop with Slowave long-term memory in under 30 minutes.

Claude Desktop requires **both**:

1. MCP server configuration so the `slowave_*` tools are available.
2. Slowave Skill upload so Claude Desktop consistently follows the memory lifecycle.

## 1. Install and verify Slowave

Recommended for isolated CLI installs:

```bash
pipx install slowave
```

Or install with pip:

```bash
pip install slowave
```

Homebrew is also available on macOS:

```bash
brew tap mrsalty/slowave
brew install slowave
```

To install from source:

```bash
git clone https://github.com/mrsalty/slowave
cd slowave
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

```bash
which slowave
which slowave-mcp
slowave --help
slowave-mcp --help
slowave stats
```

Copy the absolute path printed by `which slowave-mcp`.

## 2. Configure Claude Desktop MCP

On macOS, edit:

```text
~/Library/Application Support/Claude/claude_desktop_config.json
```

Add or merge this block, replacing `/absolute/path/to/slowave-mcp` with your actual path:

```jsonc
{
  "mcpServers": {
    "slowave": {
      "command": "/absolute/path/to/slowave-mcp",
      "env": {
        "KMP_DUPLICATE_LIB_OK": "TRUE",
        "OMP_NUM_THREADS": "1",
        "TOKENIZERS_PARALLELISM": "false"
      }
    }
  }
}
```

Restart Claude Desktop after editing the config.

## 3. Upload the Slowave Skill

Upload the packaged Skill in this directory:

```text
integrations/claude-desktop/slowave.skill
```

Claude Desktop path:

1. Open **Settings**.
2. Go to **Connectors**.
3. Click **Customize**.
4. Open **Skills**.
5. Click **Create**.
6. Click **Upload**.
7. Select `integrations/claude-desktop/slowave.skill`.

The `.skill` file is a zip archive containing `slowave/SKILL.md`. It is configured for:

```text
agent="claude-desktop"
application="claude-desktop"
```

## 4. Start the worker

Episodes are created immediately when each session ends. The worker performs offline replay/consolidation so those episodes become durable schemas for future `slowave_context` calls.

For quick testing, run this in a separate terminal:

```bash
slowave worker --interval 300
```

For daily use, install an auto-restarting user service. See [../../docs/install.md#run-consolidation-in-the-background](../../docs/install.md#run-consolidation-in-the-background).

## 5. Verify

Ask Claude Desktop:

```text
Remember that my temporary Slowave Claude Desktop test preference is chamomile tea.
```

Then run:

```bash
slowave stats
slowave recall "chamomile tea" --top-k 5 --evidence
slowave dashboard --no-open
```

Expected signs:

- Claude Desktop called `slowave_session_start`.
- It logged the user request with `slowave_event`.
- It called `slowave_context`.
- It logged at least one assistant response or completion event.
- It called `slowave_session_end`.
- `slowave recall "chamomile tea"` finds the test memory.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Claude Desktop does not show Slowave tools | Check the absolute `slowave-mcp` path, JSON syntax, and restart Claude Desktop |
| Claude Desktop sees tools but does not call them | Confirm the Slowave Skill was uploaded and enabled |
| Empty sessions | The Skill/rules are missing or ignored; verify Claude is logging `slowave_event` during the task |
| Stale/noisy memory | Use `slowave_context` for default priming; reserve `slowave_recall` for broad evidence search |
