# Feature: HTTP MCP Server (replace per-session MCP subprocess model)
## Goal
Replace the current architecture where a new MCP process (`slowave-mcp`) is spawned for every AI client session with a **single persistent HTTP MCP daemon**.
This daemon must expose MCP over HTTP so multiple AI clients (Claude Code, Cursor, Cline, Windsurf, etc.) can connect concurrently to the same memory backend.
---
## Current Problem
Current architecture:
- Each AI client session spawns a new `slowave-mcp` subprocess
- Each subprocess loads:
  - embeddings model
  - vector store / DB connection
  - memory graph state
- This causes:
  - duplicated memory state per session
  - inconsistent recall across clients
  - high startup latency
  - Windows/PATH failures
  - stale binary / version mismatches
  - no shared runtime state
---
## Target Architecture
### New model: single HTTP MCP daemon
            ┌───────────────┐

Claude Code ───►│               │
Cursor     ────►│               │
Cline      ────►│  HTTP MCP     │──► Memory DB (shared)
Windsurf   ────►│  DAEMON       │──► Embedding engine (singleton)
VS Code    ────►│               │──► Graph / retrieval layer
└───────────────┘
127.0.0.1:8765/mcp

---
## Requirements
### 1. HTTP MCP Server
Implement a persistent process:
```bash
slowave serve --mcp-http

It must:

* Bind to 127.0.0.1 only by default
* Expose MCP endpoint:

http://127.0.0.1:8765/mcp

* Support:
    * initialize
    * tools/list
    * tools/call
    * streaming responses (SSE or chunked JSON)

⸻

2. Replace per-session subprocess spawning

REMOVE current behavior:

AI Client → spawn slowave-mcp process per session

REPLACE with:

AI Client → HTTP request → persistent slowave daemon

No subprocess should be created per client session.

Only ONE backend process must exist.

⸻

3. Shared runtime state

The daemon must maintain:

* Single embedded model instance (ONNX / sentence-transformer)
* Single vector DB connection (FAISS / sqlite-vec)
* Single graph memory state
* Single cache layer
* Single session registry

All clients must share this state.

⸻

4. Backward compatibility

Keep stdio MCP for fallback:

slowave serve --mcp-stdio

But stdio must internally proxy to HTTP daemon:

stdio MCP wrapper → forwards requests to localhost HTTP daemon

NO duplicate memory logic in stdio mode.

⸻

5. Client configuration

Replace all per-client config:

BEFORE (deprecated)

{
  "mcpServers": {
    "slowave": {
      "command": "slowave-mcp"
    }
  }
}

AFTER (HTTP mode)

{
  "mcpServers": {
    "slowave": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}

⸻

6. Lifecycle compatibility layer (critical)

HTTP MCP does NOT remove lifecycle logic.

Server must still support:

* activate
* recall
* remember
* reinforce
* commit

These must be triggered via:

* tool calls OR
* optional hooks OR
* implicit session mapping inside daemon

⸻

7. Session model inside daemon

Because MCP is stateless over HTTP, implement internal session tracking:

Each client must map to:

session_id = hash(client_id + workspace + timestamp)

Store:

* session events
* tool calls
* memory updates
* embeddings
* reinforcement signals

⸻

8. Performance requirements

* First request latency < 100ms warm
* No model reload per request
* DB connections reused
* Embedding model loaded once at daemon startup

⸻

9. Observability / debug

Add:

slowave doctor

Must show:

* daemon running (yes/no)
* connected clients
* active sessions
* last recall event per client
* memory DB path
* version of daemon vs CLI

⸻

10. Migration strategy

1. Introduce HTTP daemon alongside existing stdio MCP
2. Update docs to recommend HTTP first
3. Add slowave connect auto-detection:
    * prefers HTTP if available
    * falls back to stdio otherwise
4. After stability:
    * mark subprocess-per-session mode deprecated

⸻

Acceptance Criteria

* Only ONE slowave backend process runs regardless of number of clients
* Multiple clients (Cursor + Claude Code + Cline) share same memory state
* Restarting a client does NOT reset memory state
* Memory created in one client is retrievable in another client
* No embedding model reload per session
* No per-session subprocess spawn
* slowave doctor confirms single daemon architecture

⸻

Non-goals (for now)

* Cloud sync
* Multi-machine distributed memory
* Auth beyond localhost
* UI dashboard rewrite

⸻

Rationale

This change is required to:

* eliminate per-session MCP instability
* unify cross-client memory
* reduce Windows/WSL/PATH failures
* enable true shared memory substrate across AI tools

