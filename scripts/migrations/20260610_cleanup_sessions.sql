-- Idempotent one-shot migration for Phase 1 UX refactor.
-- 
-- This script:
-- 1. Deletes sessions with ended_ts IS NULL AND no raw_events rows
--    (empty sessions created by client side-effects, never used)
-- 2. Updates remaining open sessions (ended_ts IS NULL) to ended_ts = now()
--    (so the session-idle reaper can take over after Phase 1)
-- 
-- Safe to run multiple times (the DELETE is idempotent, the UPDATE is also
-- idempotent for rows already ended).
--
-- Usage (bash):
--   sqlite3 ~/.slowave/slowave.db < scripts/migrations/20260610_cleanup_sessions.sql
--
-- Recommended workflow:
--   1. Back up: cp ~/.slowave/slowave.db ~/.slowave/slowave.db.bak-pre-ux-refactor
--   2. Apply:  sqlite3 ~/.slowave/slowave.db < scripts/migrations/20260610_cleanup_sessions.sql
--   3. Verify: SELECT COUNT(*) FROM sessions WHERE ended_ts IS NULL;  (must return 0)
--   4. Build:  uv run slowave consolidate

BEGIN TRANSACTION;

-- Delete empty sessions (no events, never contributed to episodes)
DELETE FROM sessions 
WHERE ended_ts IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM raw_events r WHERE r.session_id = sessions.id
  );

-- Close all remaining open sessions (so idle reaper can take over after Phase 1)
UPDATE sessions 
SET ended_ts = CAST(strftime('%s','now') AS INTEGER)
WHERE ended_ts IS NULL;

-- Verify: count remaining open sessions (must be 0)
SELECT 'Cleanup complete. Remaining open sessions: ' || COUNT(*) as result
FROM sessions WHERE ended_ts IS NULL;

COMMIT;
