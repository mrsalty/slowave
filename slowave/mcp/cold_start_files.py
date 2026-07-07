"""Ordered list of project documentation files the cold-start agent should inspect.

On a cold start (no memories for the current scope) the agent is instructed to
exhaust every file on this list that exists at root or in docs/, extract
durable facts from each, and encode them via slowave_remember before responding.
"""

COLD_START_FILES: list[str] = [
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "DESIGN.md",
    "ARCHITECTURE.md",
    "API.md",
    "CONTRIBUTING.md",
    "DEVELOPMENT.md",
    "ROADMAP.md",
    "CHANGELOG.md"
]
