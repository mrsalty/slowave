"""Professional output formatting for setup and cleanup commands."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from slowave.cli.output import ConsoleRenderer, Status, get_renderer


class ChangeType(str, Enum):
    """Types of changes that can be applied."""

    MCP_CONFIG = "mcp_config"
    LIFECYCLE_BLOCK = "lifecycle_block"
    HOOKS = "hooks"
    WORKER_SERVICE = "worker_service"
    BACKUP = "backup"
    DATA = "data"


class ChangeStatus(str, Enum):
    """Status of a change."""

    NEW = "new"
    UPDATE = "update"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class Change:
    """Represents a single change to be applied or removed."""

    change_type: ChangeType
    label: str  # Human-readable label
    status: ChangeStatus
    detail: str = ""  # Additional context
    path: str = ""  # File/service path

    def render(self, renderer: ConsoleRenderer) -> None:
        """Render this change using the renderer."""
        # Map change status to output status
        output_status = {
            ChangeStatus.NEW: Status.OK,
            ChangeStatus.UPDATE: Status.OK,
            ChangeStatus.SKIP: Status.SKIP,
            ChangeStatus.ERROR: Status.FAIL,
        }[self.status]

        # Build detail string
        detail_str = self.detail
        if self.path:
            detail_str = f"{self.path} ({self.detail})" if detail_str else self.path

        renderer.check(self.label, output_status, detail_str)


class SetupSession:
    """Tracks setup/cleanup operation state and results."""

    def __init__(self, operation: str = "setup", dry_run: bool = False):
        self.operation = operation  # "setup" or "cleanup"
        self.dry_run = dry_run
        self.renderer = get_renderer(use_emoji=False)
        self.changes: list[Change] = []
        self.binaries: dict[str, str] = {}
        self.manual_steps: list[str] = []
        self.errors: list[str] = []

    def add_change(self, change: Change) -> None:
        """Record a change."""
        self.changes.append(change)

    def add_binary(self, name: str, path: str) -> None:
        """Record a binary location."""
        self.binaries[name] = path

    def add_manual_step(self, step: str) -> None:
        """Record a manual step required after operation."""
        self.manual_steps.append(step)

    def add_error(self, error: str) -> None:
        """Record an error."""
        self.errors.append(error)

    def count_by_status(self, status: ChangeStatus) -> int:
        """Count changes with a specific status."""
        return sum(1 for c in self.changes if c.status == status)

    def render_header(self, title: str) -> None:
        """Render operation title."""
        self.renderer.title(title)
        if self.dry_run:
            self.renderer.warning("DRY RUN — no files will be modified", "")
        self.renderer.section("Operations")

    def render_changes(self) -> None:
        """Render all recorded changes."""
        for change in self.changes:
            change.render(self.renderer)

    def render_summary(self) -> None:
        """Render operation summary."""
        self.renderer.section("Summary")

        new_count = self.count_by_status(ChangeStatus.NEW)
        update_count = self.count_by_status(ChangeStatus.UPDATE)
        skip_count = self.count_by_status(ChangeStatus.SKIP)
        error_count = len(self.errors)

        if new_count:
            self.renderer.item("Created/installed", f"{new_count}")
        if update_count:
            self.renderer.item("Updated", f"{update_count}")
        if skip_count:
            self.renderer.item("Skipped", f"{skip_count}")
        if error_count:
            self.renderer.item("Errors", f"{error_count}", dim=False)

        if self.dry_run:
            self.renderer.section("Next Steps")
            self.renderer.item("Review", "Re-run without --dry-run to apply")

        if self.manual_steps:
            self.renderer.section("Manual Steps")
            for step in self.manual_steps:
                self.renderer.hint(step)

        # Final status
        if self.errors:
            msg = f"Setup failed with {error_count} error(s)."
            self.renderer.summary(False, msg)
        elif self.dry_run:
            msg = f"Dry run complete. {new_count + update_count} change(s) ready."
            self.renderer.summary(True, msg)
        else:
            total = new_count + update_count
            if total == 0:
                msg = "No changes applied."
            elif total == 1:
                msg = "Setup complete. 1 change applied."
            else:
                msg = f"Setup complete. {total} changes applied."
            self.renderer.summary(True, msg)
