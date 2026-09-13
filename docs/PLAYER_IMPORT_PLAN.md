# Plan: seed the real roster from the Messenger export

Implemented: see [the import guide](PLAYER_IMPORT.md) for commands and review semantics. The findings below describe the original planning snapshot. The subsequently corrected export has 54 candidate players: its first row now names Dinhduy Tran instead of containing only a badge.

## Findings from the current files and database

- Source: `tools/messenger-members/out/members.json`, a JSON array of 54 rows.
- Every row has `name`, `profileUrl`, `role`, and `photoUrl`.
- All profile and photo URLs are empty. There are no emails, team assignments, positions, ages, ratings, or shirt numbers.
- `Admin ·` appears to be a UI badge captured as a member. Exclude it from the proposed import and report it for review; its missing identity cannot be recovered from this file.
- `Duong Vu Admin ·` should propose the display name `Duong Vu`, with the original value retained in the review report.
- After those changes, there are **53 candidate players**, with no duplicate normalized names in this snapshot. This does not establish that every Messenger group member is a player or that the export is complete.
- None of the candidate names exactly matches the current demo roster after Unicode/case/whitespace normalization.
- The running PostgreSQL database contains 24 demo players, 3 demo accounts, and 23 demo matches.
- `Player.team_id` is currently required, and profile defaults supply invented soccer details if used unchanged. Some frontend labels treat every non-1 team value as Young Boys. These assumptions must be addressed before importing incomplete real profiles.

## Recommended import behavior

1. **Validate and preview first.** Build a local CLI that reads the exported file. It must not reconnect to Facebook or send messages. Reject malformed rows and invalid field types. Produce a review report listing proposed creates, explicit matches to existing players, duplicates, exclusions, and unresolved entries.
2. **Clean conservatively.** Trim and collapse whitespace, normalize Unicode, and preserve accents and original spelling. Remove only an identified trailing UI badge. Retain raw values and reasons in the report. Do not title-case, strip accents, or broadly remove words such as “Admin” from legitimate names.
3. **Keep identities explicit.** Write a local review manifest containing stable generated import IDs and any selected existing player IDs. Persist the source-to-player mapping when applying it. Repeating an import must not create duplicates. Because this export has no profile IDs, renamed or ambiguous rows require review; a display name alone must not trigger a merge into an existing player or account.
4. **Create roster profiles only.** Imported people receive no password, login account, captain flag, or admin privileges. The Messenger `role` field describes the chat and does not grant application access. An administrator can later issue the existing email-bound profile invitation after obtaining a member's email.
5. **Leave missing facts unset.** Use Messenger as the contact preference, blank optional photos/notes, and unknown values for soccer attributes. Do not fabricate ages, dominant feet, positions, shirt numbers, skill ratings, or availability. Do not create match history, statistics, or Going responses.
6. **Assign teams deliberately.** Recommended default: Unassigned until a captain/admin supplies the team assignment. Keep exactly two actual teams; Unassigned is a roster state, not a third team. If a complete team mapping is supplied before implementation, importing directly into those two teams can avoid adding an unassigned state.
7. **Keep real and demo data separate.** Recommended target: a fresh real-club PostgreSQL database with the two teams and an active season initialized and demo mode disabled. Keep the existing demo database for testing. Do not attach fabricated matches to real people, delete the existing database, or transfer demo administrator access based on names. Bootstrap a real administrator explicitly, then invite players.

## Proposed implementation

### Import service and CLI

- Add `backend/app/import_players.py` with validation, cleaning, review generation, and transactional application.
- Default to a dry run. Require an explicit apply command using the reviewed manifest and source fingerprint.
- Preserve user-edited profile fields and team assignments on later imports.
- Store minimal import provenance and unique source mappings in a small SQLAlchemy table with an Alembic migration. Keep the raw export and reports local rather than copying them into images or embedding them in seed code.
- Apply all accepted rows in one transaction; roll back on failure. Report created, matched, unchanged, rejected, and unresolved counts without printing invitation tokens or credentials.
- Support the real club database through the existing environment configuration. Inside Docker, pass the file over standard input or through a read-only runtime mount; the tools directory is outside the backend build context.

Illustrative commands, to be implemented:

```bash
# From backend/: preview, with no database changes
uv run python -m app.import_players \
  --file ../tools/messenger-members/out/members.json \
  --dry-run \
  --report ../tools/messenger-members/out/import-review.json

# Apply only the reviewed records to the configured real-club database
uv run python -m app.import_players \
  --file ../tools/messenger-members/out/members.json \
  --manifest ../tools/messenger-members/out/import-review.json \
  --apply
```

### Support for incomplete profiles

If using the recommended Unassigned workflow:

- Make primary team and unknown soccer attributes nullable, with corresponding Pydantic and TypeScript updates. Preserve existing known values.
- Display Unassigned, Unrated, or Not provided consistently across profiles, roster cards, comparisons, exports, and lineup tools.
- Update team labels, badges, avatars, filters, and admin controls so a null team never renders as Young Boys.
- Allow captains/admins to assign primary teams from the shared roster without changing prior match-side assignments.
- Allow unassigned players in mixed games. Treat unknown skill neutrally for balancing and clearly identify any fallback estimate rather than saving it as a self-rating.
- Continue deriving all statistics from actual completed matches. New players begin with zero appearances and no average rating.

### Verification

- The current file previews 53 candidates and one excluded badge-only row, with the contaminated name cleaned and reported.
- Vietnamese names and accents survive import and export unchanged apart from documented whitespace/Unicode normalization.
- Malformed input, duplicate names, name collisions, changed source files, and renamed records are handled explicitly.
- Applying the same manifest twice creates no additional players and does not overwrite subsequent profile edits.
- A failed apply leaves no partial records.
- Messenger admins receive no application privileges or automatic accounts.
- Unassigned/unknown values work in roster views, team filters, profiles, lineups, statistics, and CSV exports.
- The existing invitation flow claims the imported profile without creating a duplicate.
- Verify migrations and import behavior on SQLite and PostgreSQL, then run relevant browser workflows through Docker.

## Decisions for implementation

- **Team assignments:** import as Unassigned and assign later, or supply a mapping to Old Gentlemen / Young Boys first.
- **Roster review:** confirm the 53 candidates and resolve the unnamed `Admin ·` row if it represents a missing member.
- **Real-club setup:** identify the real administrator and use a separate database, or explicitly choose a reviewed migration of the existing demo installation.

The recommended defaults are an Unassigned roster, profile-only imports, and a separate real-club database. The preview and reviewed mapping should come before any database import.
