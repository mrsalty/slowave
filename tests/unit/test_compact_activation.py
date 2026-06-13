"""Test: compact activation fix and cosine passthrough.

Tests that CompactSchema.from_schema correctly:
1. Accepts explicit activation parameter (cosine similarity scores)
2. Falls back to saturating curve over salience when not provided
3. Saturating fallback handles spike values (e.g., salience=298.6)
"""

from slowave.mcp.compact import CompactSchema
from slowave.symbolic.schema_store import Schema
from unittest.mock import MagicMock
import math


def _make_schema(id: int, salience: float, content: str = "Test"):
    """Create a Schema mock with the minimal fields needed."""
    schema = MagicMock(spec=Schema)
    schema.id = id
    schema.content_text = content
    schema.facets = {"salience": salience, "source_kind": "explicit_remember"}
    return schema


def test_explicit_activation_preserved():
    """Explicit activation parameter is preserved verbatim."""
    schema = _make_schema(1, 10.0, "Test memory")
    
    # Explicit activation should be used directly
    compact = CompactSchema.from_schema(schema, activation=0.75)
    assert compact.activation == 0.75, f"Expected 0.75, got {compact.activation}"


def test_fallback_for_typical_salience():
    """Fallback for salience=1.4 returns > 0.2 (old bug returned ~0.07)."""
    schema = _make_schema(2, 1.4, "Spaghetti preferences")
    
    # Old bug: 1.4 / 20 = 0.07 (way too low)
    # New formula: (2/π) * arctan(1.4/2.0) ≈ (0.6366) * arctan(0.7) ≈ 0.6366 * 0.6106 ≈ 0.389
    compact = CompactSchema.from_schema(schema)
    assert compact.activation > 0.2, f"Expected > 0.2, got {compact.activation}"
    assert compact.activation < 1.0, f"Expected < 1.0, got {compact.activation}"
    print(f"Typical salience 1.4 → activation {compact.activation}")


def test_fallback_for_spike_salience():
    """Fallback for spike (salience=298.6) saturates in (0.9, 1.0]."""
    schema = _make_schema(3, 298.6, "Doctor appointment")
    
    # High salience should saturate near 1.0
    # (2/π) * arctan(298.6/2.0) ≈ 0.6366 * arctan(149.3) ≈ 0.6366 * 1.5631 ≈ 0.995
    compact = CompactSchema.from_schema(schema)
    assert 0.9 < compact.activation <= 1.0, f"Expected in (0.9, 1.0], got {compact.activation}"
    print(f"Spike salience 298.6 → activation {compact.activation}")


def test_fallback_zero_salience():
    """Fallback for zero salience returns near 0."""
    schema = _make_schema(4, 0.0, "New memory")
    
    compact = CompactSchema.from_schema(schema)
    assert compact.activation <= 0.05, f"Expected near 0, got {compact.activation}"


def test_activation_clamps_to_range():
    """Activation is always clamped to [0.0, 1.0]."""
    schema = _make_schema(5, 1.0, "Test")
    
    # Explicitly over-range
    compact = CompactSchema.from_schema(schema, activation=1.5)
    assert compact.activation == 1.0, f"Expected 1.0, got {compact.activation}"
    
    compact = CompactSchema.from_schema(schema, activation=-0.5)
    assert compact.activation == 0.0, f"Expected 0.0, got {compact.activation}"


if __name__ == "__main__":
    test_explicit_activation_preserved()
    test_fallback_for_typical_salience()
    test_fallback_for_spike_salience()
    test_fallback_zero_salience()
    test_activation_clamps_to_range()
    print("\nAll tests passed!")
