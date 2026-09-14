# Facebook sign-in and roster claiming

Status: implemented in the working tree; production deployment is pending. Selected policy: a first-time Facebook user can immediately claim any active, unclaimed profile after confirmation. No invitation or administrator approval is required.

## Outcome

A first-time Facebook user can choose any active roster profile that has no login account and connect it to the email supplied by Facebook. The original player ID, import identity, team, match history, and statistics are preserved. Successful onboarding creates a normal player account; subsequent Facebook sign-ins open that same account directly.

## Previous behavior

- `backend/app/main.py` fetches the Facebook ID but does not persist it. It finds existing accounts by email, and otherwise claims a supplied invitation or creates another player when registration is open. With registration closed and no invitation, it rejects the new user.
- `frontend/src/App.tsx` renders the login screen for everyone without a complete account. It needs to distinguish a pending Facebook sign-in from a signed-out visitor.
- `frontend/src/pages/Login.tsx` hides password login when Facebook is enabled. Existing-account linking and administrator recovery need an explicit email/password option.
- The imported roster has names but no verified login-email bindings. The selected policy uses the member's explicit profile selection; a matching Facebook name is not required.

## Member experience

1. Select **Continue with Facebook** and complete authorization.
2. If the Facebook identity is already linked, enter the club using the existing account and role.
3. Otherwise, open `/onboarding/claim-profile` with a limited onboarding session. Show the Facebook name and supplied email, with the email read-only.
4. Browse or search eligible roster profiles by name. Cards show only name, nickname, photo, and team; exclude inactive profiles and profiles that already have accounts. Any eligible profile can be selected, even when its name differs from the Facebook name. Name similarity can rank results but must not select or bind one automatically.
5. Select a profile and confirm **This is my profile**, showing the exact roster name and email to be linked. Include **My profile is missing** and **This profile is already claimed** routes to administrator assistance.
6. Confirmation immediately binds the selected profile to the Facebook identity and email, creates the login account, and issues a normal session. Show a submitting state while the transaction completes. An email-matched, valid invitation can still preselect its specific profile, but invitations are optional for general self-claim.
7. Refresh the current-user query and enter the dashboard. If someone else claimed the profile first, explain that it is no longer available and refresh the choices. If the onboarding session expired before confirmation, restart Facebook sign-in and selection; if the claim already succeeded, sign-in opens the linked account.

New roster creation remains separate. Claiming an existing profile can operate while `REGISTRATION_ENABLED=false`; enable `FACEBOOK_ROSTER_CLAIMING_ENABLED` for Facebook roster claiming. It defaults to false. When disabled, existing open-registration behavior is retained.

## Backend and identity changes

- Refactor the callback into linked, needs-onboarding, and existing-account-linking outcomes. Preserve OAuth state checks, use an explicit short expiry, and clear OAuth cookies on terminal outcomes.
- Create a short-lived, one-time onboarding token in a Secure, HttpOnly, SameSite=Lax cookie. Store its hash, expiry, the server-obtained Facebook identity/email, and completion metadata. The token is valid for 15 minutes; after completion it can only recover that same account until expiry, allowing retries after a lost response. Logout invalidates recovery through the account session version. This cookie permits only onboarding endpoints and cannot authenticate normal club APIs. Discard the Facebook access token after obtaining the necessary profile information.
- Persist an external identity keyed by provider, Facebook app ID, and Facebook user ID, linked to one `User`. Later sign-ins use that identity; changes to the Facebook email must not silently switch or merge accounts.
- If the Facebook email belongs to an existing account without a Facebook binding, offer explicit linking after authenticating that existing account, or administrator assistance. Preserve its profile and role, including the current administrator. Keep email/password sign-in available for this path.
- Use the email obtained on the server from Facebook, never an email submitted with a selected player ID. If Facebook supplies no email for a new account, show a recoverable permission/help screen; do not accept an unverified replacement email in this release.
- Introduce persistent onboarding sessions. The claim endpoint creates the user, Facebook identity binding, and email/player reservations and consumes the onboarding session in one `Store.execute` transaction. Recheck session validity, identity, email uniqueness, player activity, and absence of an existing account inside that transaction. New accounts always receive `role=player`; selection does not grant administrator or captain account privileges.
- Make retries idempotent and concurrent claims conflict cleanly with a `409` response for an unavailable profile. Recover a completed claim's result after an ambiguous network failure without creating another account. A failed transaction must leave no orphan user, reservation, or consumed invitation. Reject expired sessions and attempts to reuse a consumed session for a different claim. Cancellation or expiry before confirmation leaves the roster and accounts unchanged.
- Store the durable Facebook identity binding with its creation time and user reference, which resolves to the claimed player and email. Onboarding records retain completion time and user/session version until bounded cleanup after expiry. Do not retain OAuth access tokens or raw onboarding tokens.

## UI and API work

Add a `ClaimProfile` page and a separate onboarding route branch in `App.tsx`, outside the full member shell. Extend API types to represent signed-out, pending-selection, and fully authenticated states. The selection page handles loading, submitting, empty results, conflicts, and expired sessions.

Proposed endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /auth/onboarding` | Return the current onboarding identity, email, expiry, and eligibility to claim. |
| `GET /auth/onboarding/players?search=...` | Return a paginated list of eligible profiles with minimal display fields; allow browsing with no search term. |
| `POST /auth/onboarding/claim` | Accept the selected player ID, atomically bind the server-side identity and email, return the current user, and issue the normal session. |
| `POST /auth/onboarding/link` | Confirm the existing account password and bind Facebook while preserving its role and profile. |
| `POST /auth/onboarding/cancel` | End the onboarding attempt without creating an account. |

These routes use the existing `/api/v1` prefix. Scope candidate search and status endpoints to the onboarding session, with rate limits and the existing origin checks. Confirmation completes the entire claim flow; no review queue or separate completion endpoint is needed.

## Storage and rollout

SQL migration `d6f921acf103` adds `external_identities` and `facebook_onboarding` after the existing storage migration. Run `uv run alembic upgrade head` and `uv run alembic check` for SQL deployments. No player or user fields are changed.

Cosmos adds `externalidentity` and `facebookonboarding` document kinds within the current version 1 format. Existing documents, partition keys, and account reservations are unchanged, so no data rewrite or container reprovisioning is needed. Older backup snapshots without the new tables remain importable. Use the new backend's `python -m app.storage.cosmos.manage check` before serving traffic.

Deploy the frontend and backend together with roster claiming initially disabled. Every reader and writer must run the new backend before Facebook sign-in is used: old backends reject the new document kinds. Temporarily disable Facebook authentication during a mixed-version rollout, or cut over with no overlapping old workers. Merely disabling roster claiming does not prevent identity records from being created by existing-account linking or open registration.

Enable `FACEBOOK_ROSTER_CLAIMING_ENABLED=true` after the new revisions pass health checks. Keep `REGISTRATION_ENABLED=false` if the club should only claim existing profiles. `FACEBOOK_AUTH_ENABLED`, the app credentials, redirect URI, secure cookies, and allowed origins must also be configured. The ACA Bicep parameter is `facebookRosterClaimingEnabled`; Compose accepts the equivalent environment variable.

To disable self-claim, set the flag back to false and keep registration closed. Returning linked members can still sign in. Retain a backend that understands the new records for rollback; do not restore an older image against a container containing these records. No production data or Azure configuration was changed during implementation.

## Acceptance checks

- A new Facebook user can select any active, unclaimed profile, including one with a different name, and sign in immediately after confirmation. No invitation or administrator action is needed, and the roster count does not increase.
- The email and Facebook identity resolve to the same original player on subsequent sign-ins.
- An uncompleted or expired onboarding session cannot access normal club APIs; only a successful claim issues a normal session.
- Existing-account linking preserves role and profile; selecting another profile cannot replace an existing binding.
- Missing email, denied Facebook permissions, invalid OAuth state, duplicate names, unavailable profiles, and an empty eligible roster produce useful recovery screens.
- Two concurrent claims for one player create at most one account; replay and network retries do not duplicate bindings.
- Self-claim works with open registration disabled when the claiming flag is enabled. Invitation claims still work and cannot select a profile other than the invitation's target.
- Cancellation and expiry before confirmation create no account or player; the selected profile remains available.
- SQL and Cosmos contract tests cover atomicity and migration compatibility. Browser tests cover mobile browsing/search, immediate confirmation, the default player role, conflict recovery, return sign-in, and the email/password fallback.
