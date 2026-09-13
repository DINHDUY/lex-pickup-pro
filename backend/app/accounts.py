"""Administrator recovery CLI: python -m app.accounts reset-password EMAIL."""

import argparse
import getpass

from sqlalchemy import select

from .db import SessionLocal
from .models import User
from .security import password_hasher


def reset_password(email):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if not user:
            raise SystemExit("No account found for that email")
        password = getpass.getpass("New password (10–128 characters): ")
        if not 10 <= len(password) <= 128:
            raise SystemExit("Password must be 10–128 characters")
        confirm = getpass.getpass("Confirm new password: ")
        if password != confirm:
            raise SystemExit("Passwords do not match")
        user.password_hash = password_hasher.hash(password)
        user.session_version += 1
        db.commit()
        print("Password updated. All previous sessions have been revoked.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["reset-password"])
    parser.add_argument("email")
    args = parser.parse_args()
    reset_password(args.email)
