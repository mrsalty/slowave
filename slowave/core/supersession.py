"""Deterministic supersession. No LLM. Strong patterns only.

Runs only for explicit remember() calls, not consolidated schemas.
Pattern-based detection of belief updates and contradictions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from slowave.symbolic.schema_store import SchemaStore

# Strong supersession patterns that require explicit change signals
STRONG_SUPERSESSION_PATTERNS = [
    # Pattern 1: "now uses" - clear transition marker
    r"(?P<subject>.+?)\s+(?:now uses|is now|has moved to)\s+(?P<new_value>.+)",
    # Pattern 2: "switched from X to Y" - explicit transition
    r"(?P<subject>.+?)\s+(?:switched from)\s+(?P<old_value>.+?)\s+to\s+(?P<new_value>.+)",
    # Pattern 3: "replaced X with Y" - explicit replacement
    r"(?P<subject>.+?)\s+(?:replaced)\s+(?P<old_value>.+?)\s+with\s+(?P<new_value>.+)",
    # Pattern 4: "no longer uses X" - deprecation marker
    r"(?P<subject>.+?)\s+(?:no longer uses|dropped)\s+(?P<old_value>.+)",
    # Pattern 5: "Use X instead of Y" - imperative update
    r"Use\s+(?P<new_value>.+?)\s+instead of\s+(?P<old_value>.+)",
    # Pattern 6: "Prefer X over Y" - preference update
    r"Prefer\s+(?P<new_value>.+?)\s+over\s+(?P<old_value>.+)",
]

# Deferred (too broad for Phase 1): 
# r"(?P<subject>.+?)\s+(?:uses|is)\s+(?P<new_value>.+)"

AUTO_SUPERSEDE_THRESHOLD = 0.85


@dataclass(frozen=True)
class SupersessionCandidate:
    """A candidate schema that may be superseded by a new fact.
    
    Attributes:
        old_schema_id: ID of the potentially superseded schema
        confidence: 0.0-1.0; auto-supersede only if >= AUTO_SUPERSEDE_THRESHOLD
        reason: Human-readable description of why supersession may apply
        old_subject: The subject/entity being updated (from old schema)
        new_subject: The subject/entity in new schema (usually same as old)
        old_value: The old value being replaced (if known)
        new_value: The new value replacing it (if known)
    """
    old_schema_id: int
    confidence: float
    reason: str
    old_subject: str
    new_subject: str
    old_value: str | None
    new_value: str | None


def find_superseded_candidates(
    new_content: str,
    scope_id: str | None,
    schemas: SchemaStore,
) -> list[SupersessionCandidate]:
    """Find schemas that may be superseded by new_content using pattern matching.
    
    Performs deterministic, LLM-free pattern matching on the new content to detect
    explicit update signals ("now uses", "switched from..to", etc). When a pattern
    matches, searches for related schemas in the same scope that mention the old
    value or subject.
    
    Args:
        new_content: The new explicitly remembered fact text
        scope_id: The scope (e.g. "project:x") to search within
        schemas: The schema store for lookups and searches
        
    Returns:
        List of SupersessionCandidate objects ranked by confidence descending.
        Empty if no patterns match or no related schemas found.
    """
    candidates: list[SupersessionCandidate] = []
    
    # Compile patterns once
    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in STRONG_SUPERSESSION_PATTERNS]
    
    # Try each pattern
    for pattern_idx, pattern in enumerate(compiled_patterns):
        match = pattern.search(new_content)
        if not match:
            continue
        
        # Extract groups from match
        subject = match.group("subject").strip() if "subject" in match.groupdict() else None
        new_value = match.group("new_value").strip() if "new_value" in match.groupdict() else None
        old_value = match.group("old_value").strip() if "old_value" in match.groupdict() else None
        
        # Pattern 4 ("no longer uses") has no new_value; that's OK
        if not subject or (not new_value and pattern_idx != 3):
            continue
        
        # Confidence based on pattern specificity (lower idx = more specific)
        # All patterns should have high confidence >= 0.85 for auto-supersession
        base_confidence = max(0.90 - pattern_idx * 0.02, 0.85)
        
        # Search for candidate schemas that mention this subject/value
        # in the same scope
        candidates_from_pattern = _search_for_candidates(
            subject=subject,
            old_value=old_value,
            new_value=new_value,
            new_content=new_content,
            scope_id=scope_id,
            schemas=schemas,
            pattern_idx=pattern_idx,
            base_confidence=base_confidence,
        )
        
        candidates.extend(candidates_from_pattern)
    
    # Remove duplicates (keep highest confidence for each schema_id)
    seen: dict[int, SupersessionCandidate] = {}
    for cand in sorted(candidates, key=lambda c: c.confidence, reverse=True):
        if cand.old_schema_id not in seen:
            seen[cand.old_schema_id] = cand
    
    return sorted(seen.values(), key=lambda c: c.confidence, reverse=True)


def _search_for_candidates(
    subject: str | None,
    old_value: str | None,
    new_value: str | None,
    new_content: str,
    scope_id: str | None,
    schemas: SchemaStore,
    pattern_idx: int,
    base_confidence: float,
) -> list[SupersessionCandidate]:
    """Helper: search for schemas that match the pattern's extracted values.
    
    Uses FTS (full-text search) to find related schemas in the same scope.
    Searches by both old_value (if known) and subject to ensure we find
    schemas that mention the subject even when they don't contain old_value.
    """
    candidates: list[SupersessionCandidate] = []

    # Build search terms: always try both old_value and subject as FTS seeds.
    # Using both maximises recall — old_value misses schemas that name the
    # subject but not the exact old value, and subject alone is too broad.
    search_terms: list[str] = []
    if old_value:
        first_word = old_value.split()[0]
        if len(first_word) > 2:
            search_terms.append(first_word)
    if subject and len(subject) > 2:
        first_word = subject.split()[0]
        if len(first_word) > 2 and first_word.lower() not in [t.lower() for t in search_terms]:
            search_terms.append(first_word)

    if not search_terms:
        return []

    # All significant words of the subject (>2 chars) for post-filter validation.
    subject_words = [w.lower() for w in (subject or "").split() if len(w) > 2]

    seen_ids: set[int] = set()

    for term in search_terms:
        try:
            schema_ids = schemas.search_fts(term, limit=10, include_inactive=False)

            for old_schema_id in schema_ids:
                if old_schema_id in seen_ids:
                    continue
                seen_ids.add(old_schema_id)

                try:
                    old_schema = schemas.get(old_schema_id)
                    old_content = old_schema.content_text or ""
                except KeyError:
                    continue

                # Must be a different fact in the same scope.
                if not old_content or old_content.lower() == new_content.lower():
                    continue
                if scope_id is not None and old_schema.scope_id != scope_id:
                    continue

                # Acceptance filter: the old schema must be plausibly about the
                # same subject/value that the new fact is replacing.
                #
                # Two acceptance paths:
                #   A) old_value explicitly appears in old schema text
                #      (e.g. "switched from SQLite to DuckDB" → old schema says "uses SQLite")
                #   B) all significant subject words appear in old schema AND
                #      new_value (the replacement) does NOT already appear there
                #      (e.g. "npm switched from CommonJS to ESM" → old schema says
                #       "Using npm for package management")
                old_content_lower = old_content.lower()
                old_value_match = old_value and old_value.lower() in old_content_lower
                subject_match = (
                    subject_words
                    and all(w in old_content_lower for w in subject_words)
                    and (new_value is None or new_value.lower() not in old_content_lower)
                )

                if not old_value_match and not subject_match:
                    continue

                reason = _build_supersession_reason(
                    pattern_idx=pattern_idx,
                    subject=subject,
                    old_value=old_value,
                    new_value=new_value,
                )

                candidates.append(
                    SupersessionCandidate(
                        old_schema_id=old_schema_id,
                        confidence=base_confidence,
                        reason=reason,
                        old_subject=subject or "",
                        new_subject=subject or "",
                        old_value=old_value,
                        new_value=new_value,
                    )
                )
        except Exception:
            continue

    return candidates


def _build_supersession_reason(
    pattern_idx: int,
    subject: str | None,
    old_value: str | None,
    new_value: str | None,
) -> str:
    """Generate a human-readable reason for the supersession candidate."""
    pattern_names = [
        "now uses",
        "switched from...to",
        "replaced...with",
        "no longer uses",
        "use...instead",
        "prefer...over",
    ]
    
    name = pattern_names[pattern_idx] if pattern_idx < len(pattern_names) else "pattern"
    
    if old_value and new_value:
        return f"Pattern '{name}': {subject} updated from '{old_value}' to '{new_value}'"
    elif old_value:
        return f"Pattern '{name}': {subject} no longer uses '{old_value}'"
    elif new_value:
        return f"Pattern '{name}': {subject} now uses '{new_value}'"
    else:
        return f"Pattern '{name}' matched: possible update to {subject}"


