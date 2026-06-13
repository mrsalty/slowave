"""Generic scope helpers.

Slowave's memory model is generic. Scope strings encode context such as
``project:slowave``, ``domain:cooking``, ``relationship:alex`` or ``household``.
The format is ``<kind>:<value>`` or just ``<value>`` (kind resolves to ``generic``).
"""
from __future__ import annotations


def normalize_scope(*, scope: str | None = None) -> str | None:
    """Return a canonical scope id, or None if no scope is given."""
    if scope is not None and str(scope).strip():
        return str(scope).strip()
    return None


def scope_kind(scope: str | None) -> str | None:
    """Return the scope prefix/kind, or ``generic`` for un-prefixed scopes."""
    if not scope:
        return None
    text = str(scope).strip()
    if not text:
        return None
    if ":" in text:
        return text.split(":", 1)[0] or "generic"
    return "generic"


def scope_value(scope: str | None) -> str | None:
    """Return the value part of a scope id."""
    if not scope:
        return None
    text = str(scope).strip()
    if not text:
        return None
    if ":" in text:
        return text.split(":", 1)[1]
    return text
