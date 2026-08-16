# Database Backups

An interim `backup` sidecar service ships in both `docker-compose.yml` and `docker-compose.registry.yml`: a plain `pgvector/pgvector:pg16` container (the same image the `postgres` service pins) running `docker/scripts/backup-entrypoint.sh` on the `data` network alongside `postgres`, with no feature flag — it is always on, since a default-off backup is pointless.

## What it does

On container start, and then every `BACKUP_INTERVAL_SECONDS` (default `86400`, i.e. 24h), the script runs `pg_dump -Fc` against the `robo-fleet` database over the network (via `PGHOST=robofleet-postgres`, the same container-name resolution every other data-network consumer uses) and writes a timestamped custom-format dump to `${ROBOFLEET_DATA_DIR:-./data}/backups/robofleet-<UTC-timestamp>.dump` on the host. The dump is written to a `.tmp` suffix first and only renamed into place on success, so a crash mid-dump never leaves a half-written file that looks complete.

## Retention

After each attempt the script prunes `${ROBOFLEET_DATA_DIR:-./data}/backups` down to the newest `BACKUP_KEEP` dumps (default `14`, i.e. roughly two weeks at the default 24h cadence) by mtime, deleting the rest. There is no WAL/PITR archiving — this is a point-in-time `pg_dump` snapshot only, taken once a day.

## Off-disk mirror

By default the dumps live on the same disk as the database they protect, so a single disk failure loses both. Setting `ROBOFLEET_BACKUP_MIRROR_DIR` in `.env` to a host path on a **different** disk (an external USB disk, or a remote share the NAS OS mounts — SMB/NFS/cloud sync target) arms a mirror step: after every successful dump the script copies it into that path (same tmp+rename crash safety) and prunes the mirror to the same `BACKUP_KEEP`. Unset, the mirror is a structural no-op — the script never even attempts a copy (the compose mount then just re-points at the primary backups dir so no stray directory is auto-created). An unmounted or read-only mirror path logs a warning and skips; the primary dump is never blocked by mirror trouble. Note the semantics: each cycle mirrors only its own fresh dump — a dump whose mirror copy failed stays absent from the mirror (there is no backfill), and crash-orphaned `.tmp` files in either directory are swept at the next cycle.

Point it at a path that actually leaves the machine (e.g. a mounted cloud-synced share) if whole-host loss is in your threat model, not just disk loss.

## Failure behavior

A failed `pg_dump` (network hiccup, postgres briefly unhealthy, disk full) logs to `docker logs robofleet-backup` and is retried on the next cycle; the loop itself never exits, so the container never crash-loops on a transient failure. `restart: unless-stopped` covers the rest.

## Restoring a dump

Stop anything writing to the database, then restore into a running (empty or throwaway) `robo-fleet` database with `pg_restore`, for example: `docker exec -i robofleet-postgres pg_restore -U robo-fleet -d robo-fleet --clean --if-exists < ./data/backups/robofleet-20260711T030000Z.dump` (drop the `.tmp` files if any are present — they are in-progress dumps, not backups). Use `pg_restore -l <dump>` first if you want to inspect or selectively restore a subset of objects rather than the whole database. For a fresh empty database instead of `--clean`, create it first (`createdb -U robo-fleet robofleet_restore`) and restore into that.

## Restore drill

A backup that has never been restored is a hope, not a backup. Run this quarterly (takes ~2 minutes, touches nothing in production — it restores into a throwaway container):

```bash
# 1. Newest dump (skip any .tmp files — those are in-progress, not backups)
DUMP=$(ls -1t ./data/backups/robofleet-*.dump | head -1) && echo "$DUMP"

# 2. Throwaway postgres with the same image the stack pins
docker run -d --name robofleet-restore-drill -e POSTGRES_PASSWORD=drill \
  -e POSTGRES_USER=robo-fleet -e POSTGRES_DB=robo-fleet pgvector/pgvector:pg16
until docker exec robofleet-restore-drill pg_isready -U robo-fleet -q; do sleep 1; done

# 3. Restore the dump into it
docker exec -i robofleet-restore-drill pg_restore -U robo-fleet -d robo-fleet \
  --no-owner < "$DUMP"

# 4. Sanity-check: key tables non-empty and recent
docker exec robofleet-restore-drill psql -U robo-fleet -d robo-fleet -c \
  "SELECT (SELECT count(*) FROM tasks) AS tasks,
          (SELECT count(*) FROM agents) AS agents,
          (SELECT count(*) FROM projects) AS projects,
          (SELECT max(created_at) FROM tasks) AS newest_task;"

# 5. Tear down
docker rm -f robofleet-restore-drill
```

The drill passes when step 4 shows non-zero counts and a `newest_task` within the last backup interval. A restore error in step 3 or empty counts in step 4 means the backups are not trustworthy — investigate before you need them.

## Known ceiling

This is an interim measure, not a full disaster-recovery story: daily `pg_dump` snapshots mean up to 24h of data loss on a total failure, and there is no WAL-based continuous archiving. The off-disk mirror above covers disk loss; whole-host loss needs the mirror pointed at a path that leaves the machine. Moving to WAL/PITR archiving is the natural next step if the 24h window ever matters more than the current simplicity.
