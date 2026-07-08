"""Slowave HTTP MCP daemon.

Runs a **single persistent process** that exposes all Slowave memory tools
over HTTP (MCP streamable-HTTP transport) so multiple AI clients can connect
concurrently to the same memory backend.

  Endpoint : http://127.0.0.1:8766/mcp
  Entry    : slowave-mcp-http  (or:  slowave serve --http)
  Env vars :
    SLOWAVE_MCP_HOST          bind host (default 127.0.0.1)
    SLOWAVE_MCP_HTTP_PORT     bind port (default 8766)
    SLOWAVE_DB                database path (default ~/.slowave/slowave.db)
    SLOWAVE_MCP_IDLE_TIMEOUT  process watchdog idle timeout in seconds
                              (default 0 = disabled for the HTTP daemon;
                               unlike stdio, HTTP clients reconnect freely)

Client config (mcp_settings.json / claude.json):
  {
    "mcpServers": {
      "slowave": {
        "type": "http",
        "url": "http://127.0.0.1:8766/mcp"
      }
    }
  }
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import sys

# macOS: avoid OpenMP-duplication crashes when faiss + ONNX Runtime coexist.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")

import logging as _logging

_logging.getLogger("huggingface_hub").setLevel(_logging.ERROR)
_logging.getLogger("onnxruntime").setLevel(_logging.ERROR)

from mcp.server.fastmcp import FastMCP

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.core.paths import default_db_path
from slowave.mcp import session_reaper
from slowave.mcp.daemon import remove_pid, write_pid
from slowave.mcp.tools import register_tools
from slowave.symbolic.encoder import EncoderConfig

log = logging.getLogger(__name__)

DEFAULT_HOST = os.environ.get("SLOWAVE_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("SLOWAVE_MCP_HTTP_PORT", "8766"))
DEFAULT_DB = default_db_path()

# ---------------------------------------------------------------------------
# Engine singleton cache (same pattern as stdio server)
# ---------------------------------------------------------------------------
_ENGINES: dict[tuple, SlowaveEngine] = {}


def _build_engine(disable_encoder: bool = False) -> SlowaveEngine:
    """Return a cached SlowaveEngine for this configuration.

    The HTTP daemon is a long-lived process; the engine (embedding model,
    FAISS index, DB connection) is loaded once at first use and reused for
    the lifetime of the process across all connected clients.
    """
    key = (disable_encoder,)
    eng = _ENGINES.get(key)
    if eng is not None:
        return eng
    db_dir = os.path.dirname(os.path.abspath(DEFAULT_DB))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    cfg = SlowaveConfig(
        db_path=DEFAULT_DB,
        dim=384,
        encoder=EncoderConfig(),
        disable_encoder=disable_encoder,
    )
    eng = SlowaveEngine(cfg)
    _ENGINES[key] = eng
    return eng


# ---------------------------------------------------------------------------
# FastMCP instance with streamable-HTTP settings
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "slowave",
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
)

# Register all 7 cognitive-cycle tools from the shared module
register_tools(mcp, _build_engine)


# ---------------------------------------------------------------------------
# Build the ASGI app — streamable-HTTP + SSE + /health
# ---------------------------------------------------------------------------
def _make_app():
    """Return the FastMCP Starlette app serving both MCP transports.

    Exposes:
      GET/POST /mcp   — MCP streamable-HTTP (Claude Code, newer clients)
      GET      /sse   — MCP SSE legacy transport (Cline, older clients)
      POST     /messages  — SSE message endpoint (paired with /sse)
      GET      /health — lightweight status endpoint

    IMPORTANT: The streamable-HTTP app owns the lifespan that starts
    StreamableHTTPSessionManager.  We inject all extra routes directly into
    its router rather than wrapping it in an outer Starlette, which would
    silence the lifespan and cause 500s on every /mcp request.

    The SSE app is a plain Starlette with no critical lifespan, so it is
    safe to extract its routes and graft them in.
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from slowave import __version__

    async def health(request: Request) -> JSONResponse:
        """Lightweight health check — does not load the engine."""
        from slowave.mcp import session_resolver

        sessions = session_resolver.snapshot()
        return JSONResponse(
            {
                "status": "ok",
                "version": __version__,
                "host": DEFAULT_HOST,
                "port": DEFAULT_PORT,
                "db": str(DEFAULT_DB),
                "active_sessions": len([s for s in sessions.values() if s.get("fresh")]),
                "engines_loaded": list(_ENGINES.keys()),
            }
        )

    # Primary app — owns the lifespan; must not be wrapped
    app = mcp.streamable_http_app()

    # Graft /health into the primary app's router
    app.router.routes.insert(0, Route("/health", health, methods=["GET", "HEAD"]))

    # Graft SSE routes from the SSE app into the primary app's router
    # The SSE app has no critical lifespan so extracting its routes is safe.
    sse_app = mcp.sse_app()
    for route in sse_app.routes:
        app.router.routes.append(route)

    return app


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------
def main(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    log_level: str = "INFO",
) -> None:
    """Start the Slowave HTTP MCP daemon.

    Binds to *host*:*port* (default 127.0.0.1:8766) and serves all Slowave
    memory tools over HTTP (MCP streamable-HTTP transport).

    Enforces single-instance via PID file (~/.slowave/daemon.pid).
    Installs SIGTERM/SIGINT/SIGHUP handlers for graceful shutdown.
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="[slowave-http] %(levelname)s %(message)s",
    )

    # -- single-instance guard -----------------------------------------------
    from slowave.mcp.daemon import is_running

    if is_running():
        from slowave.mcp.daemon import read_pid

        log.error(
            "Slowave HTTP daemon is already running (pid=%d). "
            "Run 'slowave serve stop' to stop it first.",
            read_pid(),
        )
        sys.exit(1)

    pid_path = write_pid()

    # -- cleanup helpers -----------------------------------------------------
    def _cleanup() -> None:
        if _ENGINES:
            log.info("Shutting down: closing %d engine(s)...", len(_ENGINES))
            for key, engine in list(_ENGINES.items()):
                try:
                    engine.close()
                except Exception as exc:
                    log.warning("Error closing engine %s: %s", key, exc)
            _ENGINES.clear()
        remove_pid()

    atexit.register(_cleanup)

    def _signal_handler(signum: int, frame) -> None:
        sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        log.info("Received %s, shutting down...", sig_name)
        _cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _signal_handler)

    # -- session reaper (closes idle open sessions) --------------------------
    session_reaper.start(build_engine=_build_engine, poll_interval_s=120)

    # -- start server --------------------------------------------------------
    log.info(
        "Slowave HTTP MCP daemon starting on http://%s:%d/mcp  " "(pid=%d, db=%s)",
        host,
        port,
        os.getpid(),
        DEFAULT_DB,
    )

    try:
        import uvicorn

        app = _make_app()
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=log_level.lower(),
            access_log=False,
        )
    except Exception as e:
        log.error("HTTP daemon error: %s", e, exc_info=True)
        _cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()
