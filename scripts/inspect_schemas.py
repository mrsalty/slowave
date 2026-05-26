#!/usr/bin/env python3
"""
Quick script to inspect schemas in your local Slowave database.

Usage:
    python scripts/inspect_schemas.py                  # list all
    python scripts/inspect_schemas.py --search "topic" # search by query
    python scripts/inspect_schemas.py --id 1           # show schema #1
    python scripts/inspect_schemas.py --trace 1        # trace to episodes & events
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine


def list_all(eng, limit=50):
    """List all schemas with key fields."""
    schemas = eng.list_schemas(limit=limit)
    print(f"\n{'='*100}")
    print(f"Schemas ({len(schemas)})")
    print(f"{'='*100}\n")

    for s in schemas:
        print(f"[sch_{s.id}] {s.content_text}")
        print(f"  Status: {s.status:12} | Confidence: {s.confidence:.3f} | Salience: {s.salience:.3f}")
        print(f"  Class: {s.facets.get('schema_class', '?'):12} | Scope: {s.facets.get('scope', '?')}")
        print(f"  Supports: {len(s.supporting_episode_ids):3} episodes | Tags: {', '.join(s.tags)}")
        if s.needs_review:
            print(f"  ⚠️  NEEDS REVIEW")
        if s.contradicting_episode_ids:
            print(f"  ⚠️  Contradicts {len(s.contradicting_episode_ids)} schemas")
        print()


def show_schema(eng, schema_id):
    """Show full details of a schema."""
    try:
        schema = eng.get_schema(schema_id)
    except KeyError:
        print(f"❌ Schema {schema_id} not found")
        return

    print(f"\n{'='*100}")
    print(f"Schema sch_{schema_id}")
    print(f"{'='*100}\n")

    print(f"Content: {schema.content_text}\n")

    print("Metadata:")
    print(f"  Status: {schema.status}")
    print(f"  Confidence: {schema.confidence:.3f}")
    print(f"  Salience: {schema.salience:.3f}")
    print(f"  Needs Review: {schema.needs_review}\n")

    print("Facets:")
    for k, v in schema.facets.items():
        if v:
            print(f"  {k}: {v}")
    print()

    print(f"Tags: {', '.join(schema.tags)}\n")

    print(f"Supporting Episodes: {len(schema.supporting_episode_ids)}")
    for ep_id in schema.supporting_episode_ids[:5]:
        ep_text = eng.episode_text.get(ep_id)
        text = ep_text.content_text.replace("\n", " ")[:80]
        print(f"  [epi_{ep_id}] {text}...")
    if len(schema.supporting_episode_ids) > 5:
        print(f"  ... and {len(schema.supporting_episode_ids) - 5} more")

    if schema.contradicting_episode_ids:
        print(f"\nContradicts: {len(schema.contradicting_episode_ids)} schemas")


def search_schemas(eng, query):
    """Search schemas by query."""
    result = eng.recall(query, top_k=10, evidence=True)

    print(f"\n{'='*100}")
    print(f"Search Results for: '{query}'")
    print(f"{'='*100}\n")

    if result.schemas:
        print(f"Schemas ({len(result.schemas)}):")
        for s in result.schemas:
            print(f"  [sch_{s.id}] {s.content_text}")
            print(f"    Confidence: {s.confidence:.3f} | Salience: {s.salience:.3f}")
            print()
    else:
        print("No schemas found\n")

    if result.episode_texts:
        print(f"Episodes ({len(result.episode_texts)}):")
        for ep in result.episode_texts:
            text = ep['content_text'].replace("\n", " ")[:100]
            print(f"  [epi_{ep['id']}] {text}...")
        print()

    if result.raw_events:
        print(f"Raw Events ({len(result.raw_events)}):")
        for evt in result.raw_events[:10]:
            text = evt['content'].replace("\n", " ")[:80]
            print(f"  [evt_{evt['id']}] {evt['type']}: {text}...")
        if len(result.raw_events) > 10:
            print(f"  ... and {len(result.raw_events) - 10} more")


def trace_schema(eng, schema_id):
    """Trace schema → episodes → raw events."""
    try:
        schema = eng.get_schema(schema_id)
    except KeyError:
        print(f"❌ Schema {schema_id} not found")
        return

    print(f"\n{'='*100}")
    print(f"Trace: sch_{schema_id} → episodes → raw events")
    print(f"{'='*100}\n")

    print(f"Schema: {schema.content_text}\n")

    print(f"Supporting Episodes ({len(schema.supporting_episode_ids)}):")
    for ep_id in schema.supporting_episode_ids[:5]:
        ep_text = eng.episode_text.get(ep_id)
        text = ep_text.content_text[:80]
        print(f"\n  [epi_{ep_id}] {text}...")
        print(f"    Raw events: {ep_text.raw_event_ids}")

        # Show first few raw events
        for evt_id in ep_text.raw_event_ids[:2]:
            try:
                evt = eng.raw_log.get(evt_id)
                evt_text = evt.content.replace("\n", " ")[:70]
                print(f"      [evt_{evt_id}] {evt.type}: {evt_text}...")
            except KeyError:
                pass

    if len(schema.supporting_episode_ids) > 5:
        print(f"\n  ... and {len(schema.supporting_episode_ids) - 5} more episodes")


def stats(eng):
    """Show database statistics."""
    s = eng.stats()
    print(f"\n{'='*100}")
    print("Database Statistics")
    print(f"{'='*100}\n")
    for key, value in s.items():
        print(f"  {key:30} : {value}")


if __name__ == "__main__":
    db_path = Path.home() / ".slowave" / "slowave.db"
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        print("Create one first:")
        print("  slowave session start")
        sys.exit(1)

    cfg = SlowaveConfig(db_path=str(db_path))
    eng = SlowaveEngine(cfg)

    try:
        if len(sys.argv) == 1:
            # Default: list all
            list_all(eng)
            stats(eng)
        elif sys.argv[1] == "--search" and len(sys.argv) > 2:
            query = " ".join(sys.argv[2:])
            search_schemas(eng, query)
        elif sys.argv[1] == "--id" and len(sys.argv) > 2:
            schema_id = int(sys.argv[2])
            show_schema(eng, schema_id)
        elif sys.argv[1] == "--trace" and len(sys.argv) > 2:
            schema_id = int(sys.argv[2])
            trace_schema(eng, schema_id)
        elif sys.argv[1] == "--stats":
            stats(eng)
        else:
            print("Usage:")
            print("  python scripts/inspect_schemas.py                  # list all")
            print("  python scripts/inspect_schemas.py --search TOPIC   # search by query")
            print("  python scripts/inspect_schemas.py --id N           # show schema N")
            print("  python scripts/inspect_schemas.py --trace N        # trace schema N")
            print("  python scripts/inspect_schemas.py --stats          # show stats")
    finally:
        eng.close()
