"""Run hourly with cron: python -m app.reminders [--deliver]. Delivery is at least once."""

import argparse
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from .config import get_settings
from .domain.records import Match, ReminderDispatch
from .storage.factory import get_store


def dispatch_key(match):
    return f"match-{match.id}-{match.starts_at.strftime('%Y%m%dT%H%M%SZ')}-reminder"


def claim(db, match_id, owner, now):
    match = db.get(Match, match_id)
    if not match or match.status != "scheduled" or match.reminder_sent_at:
        return None
    if not now < match.starts_at <= now + timedelta(hours=24):
        return None
    key = dispatch_key(match)
    dispatch_id = hashlib.sha256(key.encode()).hexdigest()
    dispatch = db.get(ReminderDispatch, dispatch_id)
    if dispatch and (dispatch.sent_at or dispatch.lease_until > now):
        return None
    if dispatch is None:
        dispatch = ReminderDispatch(dispatch_id=dispatch_id, match_id=match_id, owner=owner, lease_until=now)
        db.insert(dispatch)
    dispatch.owner = owner
    dispatch.lease_until = now + timedelta(minutes=5)
    return {"key": key, "dispatch_id": dispatch_id, "match": match.model_dump(mode="json")}


def acknowledge(db, dispatch_id, owner, now):
    dispatch = db.get(ReminderDispatch, dispatch_id)
    if dispatch and dispatch.owner == owner and not dispatch.sent_at:
        dispatch.sent_at = now
        match = db.get(Match, dispatch.match_id)
        if hashlib.sha256(dispatch_key(match).encode()).hexdigest() == dispatch_id:
            match.reminder_sent_at = now


def run(deliver=False):
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if deliver and (
        not settings.reminder_webhook_url.startswith("https://") or not settings.reminder_webhook_secret
    ):
        raise SystemExit("Delivery requires an HTTPS REMINDER_WEBHOOK_URL and REMINDER_WEBHOOK_SECRET")
    store = get_store()
    for candidate in store.read().records(Match, status="scheduled"):
        if not now < candidate.starts_at <= now + timedelta(hours=24) or candidate.reminder_sent_at:
            continue
        owner = uuid4().hex
        delivery = None
        if deliver:
            delivery = store.execute(lambda db: claim(db, candidate.id, owner, now))
            if delivery is None:
                continue
            candidate = Match.model_validate(delivery["match"])
        when = candidate.starts_at.astimezone(ZoneInfo("America/New_York")).strftime(
            "%A, %b %d at %I:%M %p %Z"
        )
        summary = (
            f"⚽ {candidate.title}\n{when}\n📍 {candidate.location} · {candidate.pitch}\n"
            f"Please confirm Going / Maybe / Not Going.\n{settings.frontend_url}/matches/{candidate.id}"
        )
        print(summary)
        if delivery:
            payload = json.dumps(
                {"event": "match.reminder", "match_id": candidate.id, "text": summary}
            ).encode()
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
                    "Idempotency-Key": delivery["key"],
                },
            )
            response.raise_for_status()
            store.execute(
                lambda db: acknowledge(db, delivery["dispatch_id"], owner, datetime.now(timezone.utc))
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deliver", action="store_true")
    run(parser.parse_args().deliver)
