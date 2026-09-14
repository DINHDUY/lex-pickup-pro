# Deployment and club operations

For optional Azure Cosmos DB deployment, emulator development and provider migration, see [COSMOS_DB.md](COSMOS_DB.md). The SQL deployment remains the default.

## Supported topology

Place an HTTPS reverse proxy in front of the frontend container. nginx serves the compiled app and forwards `/api/` to FastAPI over a private Docker network. PostgreSQL is also private. The Compose file publishes only the web port.

1. Copy `.env.example` to `.env` at the repository root.
2. Use a **fresh PostgreSQL database**, not a demo database.
3. Set the values below for your hostname.
4. Build with `docker compose up --build -d`, or pull the CI-published images from GitHub Container Registry (see below).
5. Terminate TLS at your reverse proxy and forward to the published web port.
6. Create the first administrator interactively.

```dotenv
APP_ENV=production
WEB_PORT=8080
POSTGRES_PASSWORD=<unique-random-url-safe-password>
JWT_SECRET=<at-least-32-random-characters>
COOKIE_SECURE=true
FRONTEND_URL=https://football.example.com
CORS_ORIGINS=["https://football.example.com"]
CLUB_INVITE_CODE=<a-unique-code-for-your-club>
REGISTRATION_ENABLED=true
DEMO_ENABLED=false
```

Generate separate secrets with `openssl rand -hex 32`. Hex passwords work in the composed database URL without additional URL encoding. Do not commit `.env`. Prefer a secrets manager in managed deployments. A proxy on a public host should bind or firewall the upstream web port appropriately; only the HTTPS entry point should be exposed to members.

## GitHub Container Registry images

Club checks runs lint, unit tests, migrations, frontend build, and browser tests, then builds the backend and frontend images on every push and pull request. Images are published to GHCR only from the repository default branch and from version tags matching `v*`.

Image names follow the repository path (lowercased):

```text
ghcr.io/<owner>/<repository>/backend
ghcr.io/<owner>/<repository>/frontend
```

Default-branch builds receive `latest` plus a `sha-<short>` tag. Version tags such as `v0.1.0` also receive SemVer tags (`0.1.0`, `0.1`). Pull requests build both Dockerfiles without pushing.

Authenticate with a GitHub token that can read packages, then pull:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u USERNAME --password-stdin
docker pull ghcr.io/<owner>/<repository>/backend:latest
docker pull ghcr.io/<owner>/<repository>/frontend:latest
```

The first successful publish creates the packages. For a public repository, set each package visibility to public in GitHub Packages if anonymous pulls are required. Organization Actions settings must allow `GITHUB_TOKEN` to write packages. Local Compose still builds from `./backend` and `./frontend`; GHCR is the CI distribution path.

Create an administrator after the service is healthy:

```bash
docker compose exec backend python -m app.seed --admin-email organizer@example.com
```

This prompts for a display name and password; no password is passed on the command line or stored in shell history. It initializes the two fixed teams and an active season if needed. `REGISTRATION_ENABLED=false` closes code-based registration, while individually issued profile invitations still work.

## Azure Container Apps startup configuration

The ACA template defaults to `REGISTRATION_ENABLED=false` and `DEMO_ENABLED=false`. To enable code-based registration, set `registrationEnabled=true` and supply a unique `clubInviteCode` other than `LEX2026`.

Deploy from `infra/aca/main.bicep` when using the Azure CLI. If uploading the ARM JSON template in the portal, regenerate it after Bicep changes:

```bash
az bicep build --file infra/aca/main.bicep --outfile infra/aca/main.json
```

An older `main.json` hardcoded `REGISTRATION_ENABLED=true` while defaulting the invitation code to `LEX2026`. This fails production validation even with `DEMO_ENABLED=false`. For an existing backend, apply the closed-registration configuration without redeploying all resources:

```bash
az containerapp update \
  --resource-group "<resource-group>" \
  --name "<app-name>-backend" \
  --set-env-vars REGISTRATION_ENABLED=false DEMO_ENABLED=false \
  --output none
```

This creates a new revision. Individually issued profile invitations still work with code-based registration disabled. Container Apps receives settings from its deployment environment; editing a local `.env` file does not update a running revision.

After settings validation, startup checks Cosmos access and storage compatibility. For an existing Cosmos account, verify the [Cosmos setup requirements](COSMOS_DB.md#application-configuration-and-startup):

- `default_credential` requires an available Entra credential. The current backend uses `COSMOS_KEY` only in local emulator mode; supplying an Azure account key does not authenticate this mode.
- The account must use Strong consistency with a single write region. Consistency is an account-wide setting, including other databases in a shared account.
- The configured database/container must exist, with partition key `/club_id`, unique key `/identity_key`, and an initialized club control document.

## Authentication and authorization

- Argon2 password hashes; no plaintext password storage.
- JWTs expire after 12 hours and use a fixed accepted algorithm, issuer, and audience.
- Sessions live in HttpOnly, SameSite=Lax cookies, scoped to `/api`; production adds Secure.
- Mutating browser requests validate Origin against the explicit CORS list. Same-origin deployment avoids exposing bearer tokens to JavaScript.
- Every authenticated request checks current account activity and session version. Signing out revokes the account’s previous sessions. Password resets and privilege changes also revoke them.
- Player/captain/admin permissions are enforced on the backend, not just hidden in the UI.
- Login and registration are limited to 20 attempts per IP per 10 minutes in one process. Use a shared edge limiter for multiple workers. Only trust forwarded client-IP headers from your controlled proxy network.
- Invitation tokens are random, stored as SHA-256 hashes in invitation records (retry receipts encrypt returned links), expire after 7 days, bind to one email/profile, and are single use. Share them privately; avoid collecting full query strings in frontend access analytics.

The nginx configuration includes a content security policy, frame blocking, MIME sniffing protection, a referrer policy, and a restricted permissions policy. Authentication responses and API data use `Cache-Control: no-store`. Frontend fonts are bundled and served locally.

When nginx sits behind another load balancer or TLS proxy, configure nginx's `set_real_ip_from` and `real_ip_header` for **only that trusted proxy**, or implement the per-client limiter at the public edge. Otherwise nginx sees the upstream proxy as one shared IP and the application login limit applies to the whole club. Never trust arbitrary internet-supplied forwarding headers.

## Database lifecycle

The entrypoint runs migrations and idempotent initialization before starting the single API worker. If deploying multiple replicas, run migrations once as a release job, then start application workers separately.

```bash
# Inspect / upgrade
docker compose exec backend alembic current
docker compose exec backend alembic upgrade head

# Generate a migration during development, from backend/
uv run alembic revision --autogenerate -m "Describe schema change"
# Review the generated migration before applying it.
uv run alembic upgrade head
uv run alembic check
```

PostgreSQL serializes atomic club commands with a transaction-level advisory lock, covering RSVP admission, match mutations, identity claims and counter allocation. SQLite serializes local write requests with `BEGIN IMMEDIATE`; it is intended for local use or small single-instance demos. Never put a SQLite file on a shared network filesystem for multiple workers.

Primary teams have stable IDs: 1 = Old Gentlemen, 2 = Young Boys. Lineups hold match-side assignments independently. Deactivating a player preserves their historical appearances and event attribution. Before deactivating a member, captains should remove them from upcoming lineups and have them change any outstanding Going responses.

Back up PostgreSQL regularly:

```bash
docker compose exec -T db pg_dump -U lex -d lex_pickup -Fc > lex-pickup.backup
```

Store backups outside the application host, encrypt them, and test restoration to a separate database. `docker compose down` preserves named volumes. Adding `--volumes` permanently deletes the database volume; use it only for a disposable installation you intend to erase.

## Password recovery

Verify the member’s identity through your club’s usual channel, then run:

```bash
docker compose exec backend python -m app.accounts reset-password player@example.com
# Local equivalent, from backend/
uv run python -m app.accounts reset-password player@example.com
```

The command prompts for a new password twice and revokes all previous sessions. Deliver the new password privately. This release uses administrator-assisted recovery; it does not send reset emails.

## Scheduled reminders

Set:

```dotenv
REMINDER_WEBHOOK_URL=https://your-integration.example.com/lex-reminders
REMINDER_WEBHOOK_SECRET=<a-separate-random-secret>
```

Run hourly from your scheduler (adjust the directory):

```cron
0 * * * * cd /srv/lex-pickup-pro && docker compose exec -T backend python -m app.reminders --deliver >> /var/log/lex-reminders.log 2>&1
```

Without `--deliver`, the command prints forwardable text only. It finds scheduled games starting in the next 24 hours. Successful deliveries set `reminder_sent_at`; editing a scheduled game clears that marker so an updated reminder can be sent. Failed deliveries exit nonzero for scheduler monitoring. A conditional five-minute lease prevents overlapping workers from sending the same dispatch concurrently; the receiver must still deduplicate retries after a crash.

Webhook example:

```json
{
  "event": "match.reminder",
  "match_id": 19,
  "text": "⚽ Saturday morning football\nSaturday, Sep 19 at 10:00 AM EDT\n…"
}
```

The receiver should:

1. Compute HMAC-SHA256 of the exact raw request body using the shared secret.
2. Constant-time compare its hex digest with `X-Lex-Signature`.
3. Deduplicate the `Idempotency-Key`, such as `match-19-20260919T140000Z-reminder`.
4. Return a 2xx response only after accepting the reminder for delivery.

A failed batch or network timeout can cause a retry, so receiver-side idempotency is essential. The key includes the kickoff timestamp, so rescheduling a game allows a fresh reminder. Editing notes without changing kickoff does not trigger a duplicate message at an idempotent receiver.

Facebook personal group chats do not offer arbitrary bot posting through this app. Use an integration channel you control, or forward reminders manually. A future Meta Page chatbot requires its own supported API, permissions, and user-consent flow.

## PWA and offline behavior

The production build generates a web manifest, maskable icon, static precache, and service worker. Native install prompts are supported where available; iPhone users use Safari → Share → Add to Home Screen. HTTPS or localhost is required.

The service worker never caches `/api` responses or queues mutations. Offline users see an explicit connection message; initial sign-in/profile loading may show a retry state until connected. Already displayed data may remain in memory, but updates must be confirmed online. Update prompts let a user finish their work before reloading the new version.

## Deployment verification

- `/api/v1/health` must return `{"status":"ok"}` and database connectivity must work.
- Verify all supplied tests against the committed lockfiles.
- Sign in as a real player and captain. Confirm permissions, RSVP persistence, lineups, scoring, and sharing on a phone.
- Check that production cookies are Secure/HttpOnly and the site is served over HTTPS.
- Test backup restoration and the reminder receiver if automatic delivery is enabled.
- Check logs, disk usage, database backups, and certificate renewal in your host’s monitoring system.

No hosted deployment, Facebook credentials, TLS certificate, backup service, or external webhook is provisioned automatically by the source code.


## Facebook roster claiming

After deploying the updated frontend and backend, enable `FACEBOOK_ROSTER_CLAIMING_ENABLED=true` on the backend to let first-time Facebook members select any active profile without an account. This works with `REGISTRATION_ENABLED=false`. The selected profile is bound to the Facebook identity and server-supplied email immediately after confirmation, preserving its history and creating a normal player account.

The backend also needs `FACEBOOK_AUTH_ENABLED=true`, `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, and `FACEBOOK_REDIRECT_URI=https://www.lex-pickup-pro.us/api/v1/auth/facebook/callback`. Register that exact callback in Facebook's Valid OAuth Redirect URIs. Keep `FRONTEND_URL=https://www.lex-pickup-pro.us`, secure cookies enabled, and the frontend origin in `CORS_ORIGINS`. Existing accounts confirm their password once to link Facebook; password sign-in remains available. Facebook must supply an email for a new account.

For an already configured ACA backend, after deploying compatible images and retiring old revisions:

```bash
az containerapp update \
  --resource-group rg-lex-pickup-pro \
  --name lex-pickup-pro-backend \
  --set-env-vars FACEBOOK_ROSTER_CLAIMING_ENABLED=true REGISTRATION_ENABLED=false \
  --output none
```

The flag defaults to false. The Bicep equivalent is `facebookRosterClaimingEnabled=true`. SQL requires the new Alembic migration; Cosmos requires the new backend on all workers before any new Facebook identity records are written. See [the implementation and rollout details](FACEBOOK_ONBOARDING_PLAN.md#storage-and-rollout), including the Cosmos compatibility check and rollback constraints.
