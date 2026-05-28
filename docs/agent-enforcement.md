# Forcing coding agents to use Slowave consistently

Slowave works best when the coding agent treats memory as part of its task
lifecycle, not as an optional lookup tool. MCP configuration only makes the
`slowave_*` tools available. It does **not** force an agent to call them.

To get consistent memory, put explicit Slowave rules in the instruction surface
your agent actually reads: global rules, project rules, or the host application
that wraps the model.

## What “force” means

There are three levels of enforcement:

| Level | Mechanism | Reliability | Use when |
|---|---|---:|---|
| Tool availability | Configure `slowave-mcp` | Low | You only want manual/ad-hoc memory |
| Prompt/rules enforcement | Add lifecycle rules to `.clinerules`, `CLAUDE.md`, Cursor rules, etc. | Medium/high | Normal coding-agent use |
| Host-level hooks | Your app calls Slowave before/after model turns | Highest | Production agents/chatbots |

For local coding agents, prompt/rules enforcement is usually the practical
choice. For production systems, prefer host-level hooks so memory is called
deterministically even if the model forgets.

## Required lifecycle

Every agent integration should enforce this sequence:

1. Start a session first:
   `slowave_session_start(agent="<agent-id>", project="<repo-or-null>")`.
2. Immediately log the user request:
   `slowave_event(session_id, "user_message", "<self-contained request>")`.
3. Load a gated working-memory brief:
   `slowave_context(project="<repo-or-null>", limit=8, query="<task>", application="<agent-id>", topics=[...], entities=[...], mode="default")`.
4. During the task, log meaningful events with `slowave_event`:
   user turns, assistant responses, important tool calls/results, decisions,
   discoveries, errors, completion, and failure.
5. Use `slowave_remember` only for durable facts/preferences/decisions that
   should survive independently of the current session.
6. End the session:
   `slowave_session_end(session_id)`.

Do **not** make `slowave_recall` mandatory after `slowave_context`.
`slowave_context` is the scoped working-memory injection path; `slowave_recall`
is broad search and can intentionally return cross-project episodes or verbose
evidence. Use recall when the task needs history/provenance, not as default
prompt priming.

## Agent-specific instruction files

Use the same Slowave lifecycle rules, but place them where each agent reads
instructions.

| Agent | Best instruction location | MCP config location | Recommended ids |
|---|---|---|---|
| Cline | Global `~/.clinerules` or repo `.clinerules` | Cline MCP settings JSON | `agent="cline-tui"`, `application="cline-tui"` |
| Claude Code | Repo `CLAUDE.md`; optional user/global Claude instructions | `~/.claude/settings.json` | `agent="claude-code"`, `application="claude-code"` |
| Cursor | `.cursor/rules/*.mdc` or project rules | `.cursor/mcp.json` | `agent="cursor"`, `application="cursor"` |
| Windsurf/Cascade | Workspace/global Windsurf rules | Windsurf MCP settings | `agent="windsurf"`, `application="windsurf"` |
| OpenAI Codex-style CLIs | `AGENTS.md` or the CLI's configured instruction file | CLI/tool MCP config if supported | `agent="codex"`, `application="codex"` |
| Gemini CLI-style agents | `GEMINI.md` or the CLI's configured instruction file | CLI/tool MCP config if supported | `agent="gemini-cli"`, `application="gemini-cli"` |

If your agent does not support MCP tools directly, use the Slowave CLI from a
wrapper script, or add host-level hooks around each model turn.

## Minimal universal prompt block

Use this when you need a short instruction that fits in a project rules file:

```md
## Slowave memory rules

You have access to Slowave long-term memory via `slowave_*` tools.

At the beginning of every task:
1. Call `slowave_session_start(agent="<agent-id>", project="<repo-name-or-null>")`.
2. Store the returned `session_id` and use it for every later event.
3. Log the user request with `slowave_event(session_id, "user_message", "<self-contained summary>")`.
4. Call `slowave_context(project="<repo-name-or-null>", limit=8, query="<current task>", application="<agent-id>", topics=[...], entities=[...], mode="default")`.

During the task:
- Call `slowave_event(session_id, type, content)` for meaningful user messages,
  assistant responses, important tool calls/results, decisions, discoveries,
  errors, and task completion/failure.
- Keep event content self-contained and useful to a future session.
- Use `slowave_remember(content, type, project)` only for durable facts,
  preferences, decisions, constraints, procedures, tasks, open questions,
  warnings, lessons, or artifacts.

At the end of every task:
- Log the final assistant response.
- Log `task_complete` or `task_failed` when appropriate.
- Call `slowave_session_end(session_id)`.

Do not treat `slowave_recall` as mandatory after `slowave_context`; recall is
broad memory search and should be used only when broad history/evidence is
needed.
```

## Cline example: global `.clinerules`

This is a full example suitable for `~/.clinerules` or a repo-local
`.clinerules`. It is based on the v0.1.3 Slowave lifecycle.

```md
# Slowave — Long-Term Memory (MCP, v0.1.3)

Slowave is your long-term memory. It is **only useful if you write to it during the task**, not just at the boundaries. A session with `slowave_session_start` + `slowave_session_end` but no `slowave_event` calls in between is a **broken session** — it produces no episodic memory, no schemas, nothing to recall later.

For `project`: use the current repo/directory name for coding work (e.g. `"cimmeria"`, `"slowave"`, `"myapp"`). For non-repo chatbot work, use `null` or the app/domain scope.

## Session lifecycle — mandatory

**At the very beginning of every task**, before any other Slowave event call:

1. `slowave_session_start(agent="cline-tui", project="<repo-name-or-null>")` → store the returned `session_id`.
2. Immediately log the user turn: `slowave_event(session_id, "user_message", "<self-contained summary of the user request>")`.
3. Prime working memory with the v0.1.3 gated context API:
   `slowave_context(project="<repo-name-or-null>", limit=8, query="<current task>", application="cline-tui", topics=[...], entities=[...], mode="default")`.
4. Do **not** automatically call `slowave_recall` after `slowave_context`. `slowave_recall` is broad memory search, not scoped working-memory injection. Use it only when broad history/evidence is explicitly needed.

**During the task**: call `slowave_event(session_id, type, content)` repeatedly for every meaningful exchange or state change. Do not wait until the end.

**At task end** (always, including on failure):

- Log the final assistant response with `slowave_event(session_id, "assistant_message", "<summary of response>")`.
- Log `task_complete` or `task_failed` when appropriate.
- Call `slowave_session_end(session_id)` to encode the session into episodic memory.

## MANDATORY — when to call `slowave_event`

Call `slowave_event(session_id, type, content)` immediately when any of these happen:

| Trigger | `type` |
|---|---|
| User message, clarification, correction, or added constraint | `user_message` |
| Assistant response or substantive progress update | `assistant_message` |
| Tool invocation that matters to the work | `tool_call` |
| Tool result that changes understanding, validates work, or reveals an error | `tool_result` |
| Architectural/technical choice, tradeoff, or chosen direction | `decision` |
| Non-obvious codebase/API/environment finding | `discovery` |
| Bug, failing test, unexpected error, root cause, or fix | `error` |
| Requested unit of work is completed | `task_complete` |
| Requested unit of work fails or is abandoned | `task_failed` |

`content` should be 1–3 self-contained sentences so a future session can understand it without the surrounding chat. Include the *why*, not just the *what*.

Anti-patterns:

- Calling only `slowave_session_start` + `slowave_session_end` with no events between them.
- Batching all events into one giant event at the end.
- Logging vague narration like “ran a command” without the reason/result.
- Forgetting to use the same `session_id` returned by `slowave_session_start`.
- Treating `slowave_recall` as mandatory after `slowave_context`; this can pull broad cross-project episodic summaries into scoped tasks.

## Working-memory context: `slowave_context` v0.1.3

Use the gated working-memory brief instead of dumping high-salience memories blindly.

Signature:

`slowave_context(project, limit, query, application, topics, entities, mode)`

Arguments:

- `project`: repo/domain scope, or `null` if not applicable.
- `limit`: max schemas to inject, usually `8`.
- `query`: current task/chat cue; this is the primary relevance signal.
- `application`: caller/app cue, e.g. `"cline-tui"`, `"chatbot"`, `"mobile"`.
- `topics`: high-level topic cues, e.g. `["code review", "benchmarks"]`.
- `entities`: salient names/repos/APIs, e.g. `["Slowave", "Cimmeria"]`.
- `mode`: `"default"`, `"broad"`, or `"debug"`; use `debug` only when inspecting memory selection.

CLI equivalent when the `slowave` console script is available locally. If using only MCP tools, call `slowave_context` directly instead of shelling out.

```bash
slowave context --project <repo> --query "<task>" --application cline-tui --topic "<topic>" --entity "<entity>" --mode default --limit 8
```

## Broad memory search: `slowave_recall`

`slowave_recall(query, top_k, evidence)` is intentionally broad. It searches memory/history and may return cross-project latent summaries or prior episodes. It is useful for investigation, provenance, debugging memory behavior, comparing with previous runs/artifacts, or when the user explicitly asks for broad history.

Use `slowave_context` — not `slowave_recall` — for default task priming, scoped project context, and answers like “what do you know here/in this repo?”.

## Durable facts: `slowave_remember`

Use `slowave_remember(content, type, project)` for facts that must survive independently of any session: long-lived preferences, decisions, constraints, lessons, procedures, warnings, tasks, open questions, or artifacts. No `session_id` needed. Prefer this over `slowave_event` when the fact is durable rather than task-local.

Remember types: `fact` `preference` `decision` `constraint` `procedure` `task` `open_question` `warning` `lesson` `artifact`

## Tool reference

| Tool | When |
|---|---|
| `slowave_session_start(agent, project)` | First Slowave call at task start |
| `slowave_event(session_id, type, content)` | Every meaningful exchange/tool/result/decision/error |
| `slowave_context(project, limit, query, application, topics, entities, mode)` | Working-memory priming after session start |
| `slowave_recall(query, top_k, evidence)` | Broad memory/provenance search when needed |
| `slowave_remember(content, type, project)` | Durable cross-session fact/preference/decision/etc. |
| `slowave_session_end(session_id)` | Task end, always |
| `slowave_consolidate()` | Optional replay/consolidation after long sessions |
| `slowave_stats()` | Health check |

Common event types: `user_message` `assistant_message` `tool_call` `tool_result` `decision` `discovery` `error` `task_complete` `task_failed`
```

## Claude Code example: `CLAUDE.md`

Add a concise Slowave block to the repo's `CLAUDE.md`:

```md
## Slowave memory

Use Slowave MCP tools for every task.

- First Slowave call: `slowave_session_start(agent="claude-code", project="<repo-name>")`.
- Immediately log the user request with `slowave_event(session_id, "user_message", ...)`.
- Then call `slowave_context(project="<repo-name>", limit=8, query="<task>", application="claude-code", topics=[...], entities=[...], mode="default")`.
- During work, log meaningful `assistant_message`, `tool_call`, `tool_result`, `decision`, `discovery`, `error`, `task_complete`, and `task_failed` events.
- End every task with `slowave_session_end(session_id)`.
- Do not call `slowave_recall` by default after context; use recall only for broad history or evidence.
```

Use project `CLAUDE.md` for repo-specific behavior and user/global Claude Code
instructions for “always use Slowave” behavior across repos.

## Cursor example: `.cursor/rules/slowave.mdc`

```mdc
---
description: Use Slowave long-term memory for every coding task
alwaysApply: true
---

At task start, call `slowave_session_start(agent="cursor", project="<repo-name>")`,
log the user request with `slowave_event`, and load working memory with
`slowave_context(project="<repo-name>", query="<task>", application="cursor", limit=8, mode="default")`.

During the task, log meaningful assistant responses, tool calls/results,
decisions, discoveries, errors, and completion/failure with `slowave_event`.
At task end, call `slowave_session_end(session_id)`.

Use `slowave_recall` only when broad history/evidence is needed.
```

## Windsurf/Cascade example

Add the universal prompt block to your workspace or global Windsurf rules and
set the ids to:

```text
agent="windsurf"
application="windsurf"
```

Keep the rule short if the agent tends to ignore long policy blocks; the
non-negotiable parts are session start, user event, context, meaningful event
logging, and session end.

## Codex/Gemini-style CLI example

For agents that read repo instruction files such as `AGENTS.md`, `GEMINI.md`, or
similar, add the universal prompt block near the top of the file and set ids to
the CLI name:

```text
agent="codex"        application="codex"
agent="gemini-cli"   application="gemini-cli"
```

If the CLI does not expose MCP tools to the model, do not rely on prompt rules.
Wrap the CLI with host-level hooks instead.

## Host-level hooks for production agents

Prompt rules are useful, but production systems should call Slowave outside the
model loop:

```python
session = slowave_session_start(agent=app_name, project=project)
slowave_event(session.id, "user_message", user_message)
context = slowave_context(
    project=project,
    query=user_message,
    application=app_name,
    topics=topics,
    entities=entities,
    limit=8,
    mode="default",
)

response = model.generate(system_context=context.rendered, user=user_message)

slowave_event(session.id, "assistant_message", response.summary)
slowave_event(session.id, "task_complete", "Responded to the user.")
slowave_session_end(session.id)
```

This is the only way to guarantee calls even when the model ignores instructions.

## Verification checklist

After configuring an agent, run one small task and verify:

1. `slowave_stats()` count increases after the task ends.
2. The dashboard shows a new session/episodes.
3. The session has at least one `user_message` and one `assistant_message`.
4. `slowave_context` was called with a task-specific `query` and correct
   `application`.
5. No default rule forces `slowave_recall` after every context call.
6. A follow-up task can recall or receive the relevant memory through context.

Useful CLI checks:

```bash
slowave status
slowave stats
slowave dashboard --no-open
slowave recall "<thing you just asked the agent to remember>" --top-k 5
```

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent never calls Slowave | MCP server is configured, but rules are missing | Add lifecycle rules to the agent's instruction file |
| Empty sessions | Agent starts/ends sessions but does not call `slowave_event` | Require immediate user event and event logging during work |
| Cross-project/noisy context | Agent uses `slowave_recall` as default priming | Use `slowave_context` for working memory; reserve recall for broad search |
| Events are useless later | Content says only “ran command” or “fixed bug” | Require 1–3 self-contained sentences with reason/result |
| Wrong repo memories | Missing or stale `project`/`query` cues | Pass repo name as `project` and current task as `query` |
| Agent loses session id | Rules do not say to store/reuse `session_id` | Explicitly require reusing the returned `session_id` |
