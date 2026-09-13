"""Administrator recovery CLI: python -m app.accounts reset-password EMAIL."""

import argparse
import getpass

from .domain.records import User
from .security import password_hasher
from .storage.factory import get_store


def reset_password(email):
    store = get_store()
    if not store.read().first(User, email=email.lower()):
        raise SystemExit("No account found for that email")
    password = getpass.getpass("New password (10–128 characters): ")
    if not 10 <= len(password) <= 128:
        raise SystemExit("Password must be 10–128 characters")
    if password != getpass.getpass("Confirm new password: "):
        raise SystemExit("Passwords do not match")
    password_hash = password_hasher.hash(password)

    def update(db):
        user = db.first(User, email=email.lower())
        if not user:
            raise SystemExit("No account found for that email")
        user.password_hash = password_hash
        user.session_version += 1

    store.execute(update)
    print("Password updated. All previous sessions have been revoked.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["reset-password"])
    parser.add_argument("email")
    args = parser.parse_args()
    reset_password(args.email)
