# Messenger group member export

Attended Playwright script that opens headed Chromium, waits for a **manual** Messenger login, then exports members from a group chat you already belong to.

This is a personal operator tool. Facebook’s terms generally disallow automated collection. Do not run it unattended, against chats you cannot open in a normal browser, or in CI.

## Setup

From this directory:

```bash
npm install
npm run install-browsers
```

Requires Node.js 22+.

## Usage

1. Open the group in a normal browser and copy the thread URL (`https://www.messenger.com/t/<id>/` or `https://www.facebook.com/messages/t/<id>/`).
2. Run:

```bash
npm run extract -- --url 'https://www.messenger.com/t/<THREAD_ID>/'
```

3. If the browser shows login, 2FA, or a checkpoint, complete it in the window, then press Enter in the terminal.
4. Leave the window alone while the script clicks the thread **(i)** button, opens the right-hand **Chat info** panel, then scrolls **Chat members**. If the panel does not open, click **(i)** yourself and press Enter.

Outputs (gitignored):

- `out/members.json`
- `out/members.csv` — columns `name,profileUrl,role,photoUrl`

The Chromium profile is stored in `.auth/` so later runs can skip login while the session is valid.

### Options

| Flag | Env | Default | Meaning |
| --- | --- | --- | --- |
| `--url` | `MESSENGER_THREAD_URL` | required | Group thread URL |
| `--out` | | `./out` | Output directory |
| `--timeout-ms` | | `180000` | Navigation / pane timeouts |

## What is collected

Only what is visible in the members UI after you log in:

- Display name
- Profile URL (vanity or `profile.php?id=` when present on the row)
- Role (`admin` if an Admin badge is shown, otherwise `member`)
- Profile picture URL (CDN URL as shown; may be empty)

The list is virtualized. The script scrolls the **members pane**, not the page, until the unique count stops growing.

## Troubleshooting

- **Checkpoint / suspicious login.** Finish it in the headed window, then press Enter. Persistent `.auth/` usually avoids this on the next run.
- **Could not open Chat info.** Click the **(i)** button in the thread header so the right panel shows Chat members, then press Enter when the script pauses — or re-run after that panel is already open.
- **Empty list / debug.png.** Harvest reads **Chat members** rows (`Name` + `Added by …`) in the right panel. Profile URLs are optional. If `debug.png` shows that list but export is empty, Messenger restyled the pane — adjust harvest in `extract.mjs`.
- **Count lower than Messenger’s header.** The list did not finish virtualizing. Re-run; if it still short, increase the stable-tick loop in `collectMembers`.
- **Session expired.** Delete `.auth/` and log in again.

This tool does not import members into Lex Pickup Pro.

## Import into Lex Pickup Pro

Use the [roster import guide](../../docs/PLAYER_IMPORT.md) to preview `out/members.json`, review identities, and import profiles into the separate real-club database. Exporting this list does not create app accounts or grant permissions. Keep `out/import-review.json` with the local export for repeat imports.
