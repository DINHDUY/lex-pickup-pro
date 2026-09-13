"""Run hourly with cron: python -m app.reminders [--deliver]."""

import argparse
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import Match


def run(deliver=False):
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if deliver and (
        not settings.reminder_webhook_url.startswith("https://") or not settings.reminder_webhook_secret
    ):
        raise SystemExit("Delivery requires an HTTPS REMINDER_WEBHOOK_URL and REMINDER_WEBHOOK_SECRET")
    with SessionLocal() as db:
        matches = db.scalars(
            select(Match)
            .where(
                Match.status == "scheduled",
                Match.starts_at > now,
                Match.starts_at <= now + timedelta(hours=24),
                Match.reminder_sent_at.is_(None),
            )
            .with_for_update()
        )
        for m in matches:
            start = m.starts_at.replace(tzinfo=timezone.utc) if m.starts_at.tzinfo is None else m.starts_at
            when = start.astimezone(ZoneInfo("America/New_York")).strftime("%A, %b %d at %I:%M %p %Z")
            summary = (
                f"⚽ {m.title}\n{when}\n📍 {m.location} · {m.pitch}\n"
                f"Please confirm Going / Maybe / Not Going.\n{settings.frontend_url}/matches/{m.id}"
            )
            print(summary)
            if deliver:
                payload = json.dumps({"event": "match.reminder", "match_id": m.id, "text": summary}).encode()
                signature = hmac.new(
                    settings.reminder_webhook_secret.encode(), payload, hashlib.sha256
                ).hexdigest()
                response = httpx.post(
                    settings.reminder_webhook_url,
                    content=payload,
                    timeout=15,
                    headers={
                        "Content-Type": "application/json",
                        "X-Lex-Signature": signature,
                        "Idempotency-Key": f"match-{m.id}-{start.strftime('%Y%m%dT%H%M%SZ')}-reminder",
                    },
                )
                response.raise_for_status()
                m.reminder_sent_at = now
        if deliver:
            db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deliver", action="store_true")
    run(parser.parse_args().deliver)
