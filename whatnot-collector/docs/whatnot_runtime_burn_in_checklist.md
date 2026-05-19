# Whatnot Runtime Burn-In Checklist

Use this checklist for the next `2-3` real live Whatnot sessions only.

## Goal

Validate that the Whatnot runtime is stable on:

- `Postgres-primary` ingest/write paths
- `Postgres-backed` `events_db.py` reads
- `Postgres-backed` `api.py` Whatnot runtime reads

This checklist is only for the Whatnot runtime scope.

## Before Each Session

Run:

```bash
cd "/home/cybertechna/AethrixSystems_Portable/hjay9672-WN /whatnot-collector"
python3 -m server.company_cutover_verify
python3 -m server.ingest_streams_verify
python3 -m server.ingest_events_verify
python3 -m server.ingest_failed_verify
python3 -m server.ingest_users_verify
python3 -m server.ingest_lots_verify
python3 -m server.ingest_stream_merge_verify
tail -n 50 data/postgres_cutover_mismatches.jsonl
```

Confirm in [`.env`](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/.env):

- `DB_PRIMARY_INGEST_STREAMS=postgres`
- `DB_PRIMARY_INGEST_STREAM_MERGE=postgres`
- `DB_PRIMARY_INGEST_EVENTS=postgres`
- `DB_PRIMARY_INGEST_USERS=postgres`
- `DB_PRIMARY_INGEST_LOTS=postgres`
- `EVENTS_DB_READ_BACKEND=postgres`
- `EVENTS_DB_VALIDATE_READS=1`
- `ALLOW_SQLITE_RUNTIME=0`
- `COLLECTOR_SQLITE_FALLBACK_ENABLED=0`

Start collector:

```bash
WHATNOT_STREAM_URL="https://www.whatnot.com/live/<LIVE_ID>" HEADLESS=false xvfb-run -a .venv/bin/python -m src.collector.main
```

## During Each Session

Every `10-15` minutes, run:

```bash
python3 -m server.ingest_events_verify
python3 -m server.ingest_failed_verify
python3 -m server.ingest_users_verify
python3 -m server.ingest_lots_verify
python3 -m server.ingest_streams_verify
python3 -m server.ingest_stream_merge_verify
tail -n 20 data/postgres_cutover_mismatches.jsonl
```

Also confirm in the app/runtime:

- lots are appearing
- usernames are appearing
- winner info is appearing
- prices are appearing
- `/events` and `/recent` stay live
- winner assignment queue stays current
- spectator diagnostics still loads

## Expected Clean Thresholds

All of these should remain clean:

- `ingest_streams_verify`: `ok: true`
- `ingest_events_verify`: `ok: true`
- `ingest_failed_verify`: `ok: true`
- `ingest_users_verify`: `ok: true`
- `ingest_lots_verify`: `ok: true`
- `ingest_stream_merge_verify`: `ok: true`
- `company_cutover_verify`: `ok: true`

Expected behavior:

- row counts match
- newest IDs match
- latest event resolution matches
- stream identity lookups match
- no orphaned stream references
- no `events_db_reads` mismatch entries added
- no new merge-domain mismatch growth

## Hard-Stop / Rollback Triggers

Pause immediately if any of these appear:

- newest event mismatch
- missing lot updates
- missing usernames
- missing winner info
- missing prices
- stream identity lookup differs
- merged source stream still exists in one DB only
- dependent rows still point to deleted `source_id`
- `events_db_reads` mismatch log starts growing
- any ingest verifier flips to `ok: false`
- collector stays running but live data stops landing correctly

Immediate rollback path:

1. stop the affected collector/runtime process
2. capture verifier output and the tail of `data/postgres_cutover_mismatches.jsonl`
3. only if an approved rollback is required, set `ALLOW_SQLITE_RUNTIME=1` and the affected domain/read flag back to `sqlite`
4. restart collector/runtime process
5. keep validation on

## After Each Session

Run:

```bash
python3 -m server.ingest_streams_verify
python3 -m server.ingest_events_verify
python3 -m server.ingest_failed_verify
python3 -m server.ingest_users_verify
python3 -m server.ingest_lots_verify
python3 -m server.ingest_stream_merge_verify
python3 -m server.company_cutover_verify
tail -n 100 data/postgres_cutover_mismatches.jsonl
```

## Session Verdict

Verdict: `PASS` / `PASS WITH WARNINGS` / `FAIL`

Use:

- `PASS`
  all verifiers clean, no mismatch growth, no rollback, live data normal
- `PASS WITH WARNINGS`
  verifiers clean but non-blocking collector/runtime warnings occurred
- `FAIL`
  any hard-stop condition, rollback used, or live data missing/drifting

## Session Log Template

Copy this block for each live session:

```text
Session #: 
Verdict: PASS / PASS WITH WARNINGS / FAIL

Stream URL:
Stream ID:
Start Time:
End Time:

Before Session:
- ingest_streams_verify:
- ingest_events_verify:
- ingest_failed_verify:
- ingest_users_verify:
- ingest_lots_verify:
- ingest_stream_merge_verify:
- company_cutover_verify:

During Session Notes:
- lots appearing:
- usernames appearing:
- winner info appearing:
- prices appearing:
- /events and /recent healthy:
- winner assignment queue healthy:
- spectator diagnostics healthy:

Mismatch Delta:
- total mismatch lines before:
- total mismatch lines after:
- events_db_reads delta:
- ingest/merge delta:

Collector Warnings:
- none / list warnings

Rollback Used:
- no / yes
- if yes, what changed:

Final Notes:
- 
```

## Final Sign-Off

Only sign off after `2-3` real live Whatnot sessions all finish clean.

### Disable Reverse Shadow

Ready when all are true:

- all Whatnot runtime burn-in sessions are `PASS` or acceptable `PASS WITH WARNINGS`
- no parity drift across ingest/read verifiers
- no mismatch log growth for Whatnot runtime domains
- no rollback was required for a data-integrity reason

Sign-off:

- [ ] Disable Whatnot runtime reverse shadow
- Date:
- Approved by:
- Notes:

### Declare Whatnot Runtime SQLite-Free

Ready when all are true:

- live collector writes are stable on Postgres paths
- stream merge/canonicalization is stable
- `events_db.py` Whatnot runtime reads are stable on Postgres
- `api.py` Whatnot runtime reads are stable on Postgres
- live Whatnot sessions work end-to-end without SQLite dependence

Sign-off:

- [ ] Declare Whatnot runtime SQLite-free
- Date:
- Approved by:
- Notes:

### Archive SQLite For Whatnot Scope

When the Whatnot runtime is declared SQLite-free:

1. freeze the SQLite DB used for Whatnot rollback
2. record timestamp, size, and checksum
3. store it as read-only archive
4. remove Whatnot runtime dependency on SQLite config/runtime paths

Sign-off:

- [ ] Archive SQLite for Whatnot scope
- Archive path:
- Checksum:
- Date:
- Approved by:
- Notes:
