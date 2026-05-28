# Slowave integrations

This directory is the fastest path from a fresh install to working long-term memory in a client.

Target: **under 30 minutes** for one client.

## Pick your client

| Client | Guide | Required setup |
|---|---|---|
| Claude Desktop | [claude-desktop/](claude-desktop/) | Install Slowave, configure MCP, upload `slowave.skill`, start worker, verify |
| Claude Code | [claude-code/](claude-code/) | Install Slowave, configure MCP, add `CLAUDE.md` rules, start worker, verify |
| Cline | [cline/](cline/) | Install Slowave, configure MCP, add `.clinerules`, start worker, verify |

## The non-negotiable rule

Every client needs three things:

1. **MCP server configuration** so the `slowave_*` tools are visible.
2. **Instruction/rules injection** so the client actually calls those tools.
3. **Background worker** so episodes are consolidated into durable schemas over time.

MCP alone is not enough. If the model can see Slowave but is not instructed to start sessions, log events, load context, and end sessions, memory will be sparse or empty. If the worker is not running, sessions still form episodes immediately, but distilled schemas and future `slowave_context` quality will lag until you run `slowave worker --once` or start the worker.

## Shared install check

Install Slowave once:

```bash
pipx install slowave
# or: pip install slowave
# or: brew tap mrsalty/slowave && brew install slowave
```

Verify:

```bash
which slowave
which slowave-mcp
slowave --help
slowave-mcp --help
slowave stats
```

Use the absolute path printed by `which slowave-mcp` in your client MCP config.

## Start the worker

For quick local testing, run this in a separate terminal:

```bash
slowave worker --interval 300
```

For daily use, install it as a user service so it restarts after reboot/crash. See [../docs/install.md#run-consolidation-in-the-background](../docs/install.md#run-consolidation-in-the-background).

## Verification task

After configuring a client, ask it:

```text
Remember that my temporary Slowave integration test preference is chamomile tea.
```

Then verify in a terminal:

```bash
slowave stats
slowave recall "chamomile tea" --top-k 5 --evidence
slowave dashboard --no-open
```

A working setup should show a new session/events/episodes and should recall the test preference.

## Canonical references

- [../docs/install.md](../docs/install.md): install, MCP, troubleshooting.
- [../docs/agents.md](../docs/agents.md): tool lifecycle and semantics.
- [../docs/agent-enforcement.md](../docs/agent-enforcement.md): prompt/rules templates.
