# Optional Azure Cosmos DB storage

Lex Pickup Pro supports `DATABASE_PROVIDER=sql` (default: PostgreSQL or SQLite) and `DATABASE_PROVIDER=cosmos` (Azure Cosmos DB **for NoSQL**). A deployment uses one provider. Database failures return an error; there is no fallback or dual writing. Existing SQL deployments need the new Alembic migration when upgrading the application.

The API routes, integer IDs, teams, account roles, nullable player fields, analytics and Messenger summaries are shared between providers. Cosmos does not require a PostgreSQL service or run Alembic. The existing SQL demo and real-club volumes are independent of the Cosmos demo below.

## Local Docker demo

```bash
# Repository root. Separate project and volumes; app on 8082.
docker compose -p lex-cosmos -f compose.cosmos.local.yaml up --build -d
```

Open **http://localhost:8082**. Demo accounts remain `admin@lexpickup.club`, `captain@lexpickup.club`, and `player@lexpickup.club`, password `PickupPro2026!`. The demo has 24 players and 23 matches. Its session cookie has a distinct name so signing in does not replace the SQL demo's cookie.

The pinned Linux vNext emulator supports ARM64 and AMD64. Its API is bound to **127.0.0.1:18081**, and Data Explorer to **127.0.0.1:11234**. The public emulator key is confined to development mode; production rejects emulator credentials. First startup can take a minute. The initializer explicitly creates the database/container and control document; API startup only validates resources and initializes club/demo records.

```bash
docker compose -p lex-cosmos -f compose.cosmos.local.yaml logs --tail=40 backend
docker compose -p lex-cosmos -f compose.cosmos.local.yaml exec backend python -m app.storage.cosmos.manage check
docker compose -p lex-cosmos -f compose.cosmos.local.yaml down
```

`down` preserves the named emulator volume. Treat emulator data as disposable: it is not a backup service or a substitute for an Azure restore exercise. The emulator does not reproduce production RU charges, latency, all index behavior or Azure's multi-client consistency guarantees.

## Azure resources and identity

Use [infra/azure/cosmos.bicep](../infra/azure/cosmos.bicep). It provisions:

- A NoSQL account with **Strong** consistency, one write region, provisioned throughput (initially 400 RU/s), TLS 1.2, disabled account-key authentication and seven-day continuous backup.
- Database/container, `/club_id` partition key, unique `/identity_key` policy and indexes.
- Container-scoped Cosmos data-plane contributor assignments for the backend managed identity and an optional operator identity. Azure management-plane Contributor alone is insufficient.
- Explicit firewall IPs or a private endpoint, private DNS zone/link, and metric alerts for throttling, server errors, latency, RU pressure and storage growth. Supply an action group for alert delivery.

Create/attach the backend's managed identity through your hosting platform. `backendPrincipalId` is its **object/principal ID**. `COSMOS_MANAGED_IDENTITY_CLIENT_ID` is the optional **client ID** of a user-assigned identity. System-assigned identity leaves that setting empty.

Review parameters before provisioning. The template creates no hosting service. With neither firewall IPs nor a private endpoint, the account intentionally has no public access. For private networking, supply both subnet and VNet IDs; ensure the backend and operator can resolve/reach the private endpoint. Reuse existing private DNS infrastructure through a template adaptation if your subscription already manages that zone centrally.

```bash
az login
az bicep build --file infra/azure/cosmos.bicep --outfile /tmp/lex-cosmos.json
# Use a reviewed parameter file with account name, region, identity IDs and network settings.
az deployment group what-if --resource-group YOUR_RESOURCE_GROUP \
  --template-file infra/azure/cosmos.bicep --parameters @cosmos.parameters.json
az deployment group create --resource-group YOUR_RESOURCE_GROUP \
  --template-file infra/azure/cosmos.bicep --parameters @cosmos.parameters.json
```

400 RU/s is a starting configuration, not a price/performance claim. Strong reads have a higher RU cost than weaker consistency. Measure dashboard, export, authentication and write workloads in the selected Azure region. Change throughput and alert thresholds based on measurements. Single-partition storage and serialization deliberately target a small recreational club, not a large multi-tenant platform.

## Application configuration and startup

Copy [.env.cosmos.example](../.env.cosmos.example) to `.env.cosmos` and replace the placeholders. Use fresh secrets for a new deployment; preserve `JWT_SECRET` when migrating an existing deployment if its sessions and encrypted command receipts must remain usable. Store secrets in your hosting platform's secret manager.

```dotenv
DATABASE_PROVIDER=cosmos
COSMOS_ENDPOINT=https://YOUR-ACCOUNT.documents.azure.com:443/
COSMOS_DATABASE=lex_pickup_real
COSMOS_CONTAINER=club_data
COSMOS_CLUB_ID=lex-pickup
COSMOS_AUTH_MODE=managed_identity
COSMOS_CONSISTENCY_LEVEL=Strong
```

For host development with an authorized Azure CLI account, select `COSMOS_AUTH_MODE=default_credential`. DefaultAzureCredential can also use appropriately configured workload/environment credentials. Docker does not inherit the host's `az login`; use an Azure host with managed identity or explicitly configure the container's credential path. The standalone remote Compose file assumes that credential path is already available.

Initialize an empty provisioned container once, **before starting API replicas**. `--entrypoint` bypasses normal readiness checks for this administrative action:

```bash
docker compose --env-file .env.cosmos -f compose.cosmos.yaml run --build --rm \
  --entrypoint python backend -m app.storage.cosmos.manage init
docker compose --env-file .env.cosmos -f compose.cosmos.yaml up --build -d
# Bootstrap an admin, or bind to an explicitly selected imported player ID.
docker compose --env-file .env.cosmos -f compose.cosmos.yaml exec backend \
  python -m app.seed --admin-email organizer@example.com --admin-player-id 1
```

Terminate HTTPS in your host/reverse proxy before exposing a production deployment. Registration, JWT cookies, Facebook configuration and CORS retain their existing controls.

Both the Docker entrypoint and normal API-worker startup check Cosmos compatibility. A container with a wrong partition key, missing unique policy, unknown document version, invalid identity reservations, unavailable storage, maintenance mode or an incompatible consistency configuration is rejected. `/api/v1/health` performs a control-document point read and fails during maintenance.

`python -m app.storage.cosmos.manage check` validates configuration and all records. `upgrade` currently performs the same check: version 1 is the first supported document format, so there is no older format to transform. Unknown versions are never silently rewritten; future changes must add an explicit maintenance-mode transform here. Alembic is exclusively for SQL.

## Storage behavior and limits

Domain records and validation live in `app/domain`; routes, analytics and operational CLIs use those records. The adapters live in `app/storage/sql` and `app/storage/cosmos`. Pure commands run on a private club snapshot and commit through `Store.execute`. They can be retried without sending a webhook, rerunning an OAuth exchange, or prompting for a password again.

Cosmos stores all club records in one trusted server-selected `club_id` partition. Players embed import provenance; matches embed RSVP, lineup, event and rating records. Accounts have email reservations and a unique player identity. Invitations have token-hash IDs and a per-player pointer. Public API responses contain none of this metadata.

Reads consume every query continuation page, bounded by `COSMOS_MAX_DOCUMENTS` (10,000 domain/reservation documents) and `COSMOS_MAX_SNAPSHOT_BYTES` (32 MB). A control-document ETag read before/after pagination prevents mixing snapshots from concurrent commands. These are deliberate initial limits; exceeding them returns an error instead of truncating history. Whole-club reads cost more than targeted reads. Profile on Azure before increasing the limits or adding materialized summaries.

Every write conditionally replaces the same control document plus changed records and a command receipt in one transaction. This serializes concurrent club commands, including final-place RSVP admission, invitation claims, ID allocation and season changes. SQL uses a club-level PostgreSQL advisory lock or SQLite `BEGIN IMMEDIATE` for the same boundary. Authorization and business rules run again after a conflict.

Cosmos rejects live commands before sending writes when they exceed 100 operations, a conservative 1.9 MB request budget (including per-operation overhead), or a 1.8 MB item budget. A fresh 54-player import uses about 56 operations. Larger SQL imports remain supported. Oversized Cosmos imports are **not** split into independently committed chunks. Offline migration can chunk because its target remains unavailable until verification.

API mutations accept `Idempotency-Key` (16–128 URL-safe characters). Use the same key and payload to retry a request whose outcome is unknown. Receipts and domain changes commit atomically; timeout recovery checks the receipt before replaying. Conflicts/throttling/network retries are bounded. The browser retains uncertain keys in memory for retries in the same page session. After reloading following an uncertain result, inspect the match/account before repeating the action; offline mutation queues are not provided.

Receipt results are encrypted with a key derived from `JWT_SECRET`, including invitation links. Hashes, roles and session versions are preserved during migration. Receipts currently have no automatic expiry, retaining idempotency across migrations; include their growth in storage monitoring. Signing-secret rotation invalidates old sessions and makes earlier receipts unreadable. Do not rotate it during a storage cutover.

Reminders use a five-minute conditional lease, send outside the transaction, and acknowledge the matching owner. Failed/crashed deliveries can be reclaimed. Delivery remains at least once; receivers must honor the existing deterministic `Idempotency-Key`. Stop scheduled jobs and let in-flight webhook requests finish before a final migration export.

## Migrate SQL to Cosmos, or restore Cosmos to SQL

No migration changes an environment file, routes traffic, deletes the source, or overwrites an existing target. Test with a copy first. Keep a normal PostgreSQL backup as well as the portable snapshot. Export files include private account hashes and roster data: created files are mode 0600, existing files are never overwritten, and import rejects group/world-readable files. Keep them outside the repository on encrypted storage.

All commands below run from `backend/` with **one explicitly selected provider/environment**. Use `uv run --env-file /absolute/path/source.env ...` / `target.env`; do not put credentials in command arguments. Cosmos settings do not affect a SQL source. Select a distinct empty target database/partition.

1. Upgrade the SQL source schema using `uv run --env-file /path/source.env alembic upgrade head` after backing up and coordinating the application release. Do not run old and new application versions simultaneously during the cutover.
2. Provision and initialize the Cosmos target, but do **not** seed or start it. A restore requires an empty target. Keep existing traffic on SQL.
3. Export a planning preview and inspect the dry-run counts/limits:

   ```bash
   uv run --env-file /path/source.env python -m app.migrate_storage export --output /secure/preview.json
   uv run --env-file /path/target.env python -m app.migrate_storage import --input /secure/preview.json
   ```

4. Stop reminder jobs/in-flight deliveries and pause application traffic. Freeze the source and export a final snapshot:

   ```bash
   uv run --env-file /path/source.env python -m app.migrate_storage export --freeze --output /secure/final.json
   ```

   The maintenance gate blocks reads and writes. If export fails, the source may remain frozen; inspect the failure before `resume`. A live preview cannot be applied as a final migration.

5. Apply the snapshot to the inactive target, then verify:

   ```bash
   uv run --env-file /path/target.env python -m app.migrate_storage import --input /secure/final.json --apply
   uv run --env-file /path/target.env python -m app.migrate_storage verify --input /secure/final.json
   ```

   Cosmos writes at most 75 records per checkpointed chunk, further reduced for request size. Rerun the same import after interruption/timeout; the checkpoint and records commit together. A different snapshot is rejected. Counts, canonical record/counter hashes, relationships, provenance, encrypted receipts, derived reservation documents and analytics must match. The target remains in maintenance after a successful import.

6. Activate the verified target, then change **one** application's configuration/traffic routing and resume reminders:

   ```bash
   uv run --env-file /path/target.env python -m app.migrate_storage activate --input /secure/final.json
   ```

   Record the snapshot checksum and cutover time. Verify sign-in, roles, roster, invitation claims, RSVP, lineups, results, exports and Messenger summaries. Keep the old source frozen and backed up.

Before any new target writes, rollback can resume the original source. **After new target writes, simply switching back loses those changes.** Freeze/export the current Cosmos state, then import it into a **new empty SQL database** (run Alembic first, without seeding). Verify/activate it and switch traffic there. The same command set supports this reverse transfer and preserves IDs, nulls, Unicode, account hashes, sessions, import UUIDs and command receipts. Never restore on top of the old SQL source. `pause` / `resume` are explicit maintenance controls; `resume` refuses an unfinished Cosmos restore.

## Tests and rollout gate

```bash
cd backend
uv run pytest -q
# Real SDK against the locally running emulator; creates disposable test-* partitions.
LEX_TEST_COSMOS_ENDPOINT=http://localhost:18081 uv run pytest -q

# Existing isolated Azure account/container, Strong, single write region, correct unique policy:
LEX_TEST_COSMOS_ENDPOINT=https://YOUR-TEST-ACCOUNT.documents.azure.com \
LEX_TEST_COSMOS_DATABASE=lex_test_acceptance \
LEX_TEST_COSMOS_CONTAINER=club_data uv run pytest -q tests/storage
```

Azure tests require an authorized DefaultAzureCredential identity, network access and an already provisioned **lex_test_*** database. They create/delete only randomly named test partitions. Do not point them at the real-club database. Tests cover both adapters, actual SDK batches/ETags/unique keys, concurrent admissions/claims, import preservation/rollback/limits, encrypted receipts, session revocation, pagination, leases, migration checksums and interrupted/reverse restores. A deterministic container double injects throttling, stale reads and lost commit responses; it complements the SDK integration suite.

The browser suite runs against SQL by default. To test the **disposable** Cosmos demo:

```bash
cd frontend
E2E_BASE_URL=http://localhost:8082 npm run test:e2e
```

Repeated browser runs within ten minutes can hit the login limiter. For this disposable local demo only, restart its backend before another complete run; keep production rate limits enabled.

Before a real cutover, run the Azure suite from two independent clients/workers, measure RU and latency, verify private connectivity/managed identity/alerts, and exercise Azure continuous-backup restoration to a new account. The same database-independent `verify` command can compare a restored account's selected checkpoint to its matching export. Reapply managed-identity permissions/network configuration on the restored account before serving traffic. Emulator/export round trips do not prove Azure point-in-time recovery, RU budgets or regional behavior.

No Azure resources or real-club cutover were performed during local implementation. Live validation remains a rollout gate; the cached Azure sign-in in this workspace had expired. Region, hosting identity, network, action group and operating budget must be selected for that deployment.

### Local verification, 2026-09-13

- Backend suite with the real ARM64 emulator: **118 passed**, 12 provider-specific skips.
- Existing PostgreSQL API/import suite: **52 passed**; PostgreSQL migration, schema-drift, seed and API smoke checks passed.
- Playwright: **14 desktop/mobile checks passed on SQL and 14 on the Cosmos Docker demo**, including invitations, lineups, scoring, sharing and accessibility.
- Frontend lint/build, Docker build/startup, and Bicep compilation passed.
- An isolated copy of the real club completed PostgreSQL → Cosmos → PostgreSQL migration with matching counts/checksums: **54 players, 54 import identities, one existing account and both teams**. Private test copies were removed afterward. The original SQL database and its migration version were unchanged.
- Azure RU/latency, managed identity/private networking, multi-region service behavior and continuous-backup restoration remain unverified until the live Azure rollout checks are run.
