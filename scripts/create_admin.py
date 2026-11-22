#!/usr/bin/env python3
"""
Bootstrap script — creates the first admin account.

Usage:
    python scripts/create_admin.py --username admin --password <secret>

Run from the project root so that relative paths in config.py resolve correctly.
"""

import argparse
import sys
import os
from datetime import datetime, timezone

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import database, config
from backend.auth import hash_password


def main():
    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument("--username", required=True, help="Admin username")
    parser.add_argument("--password", required=True, help="Admin password (min 8 chars)")
    args = parser.parse_args()

    if len(args.password) < 8:
        print("Error: password must be at least 8 characters", file=sys.stderr)
        sys.exit(1)

    database.init_db()

    existing = database.get_user_by_username(args.username)
    if existing is not None:
        print(f"Error: username '{args.username}' already exists", file=sys.stderr)
        sys.exit(1)

    user_id = database.create_user(
        username=args.username,
        password_hash=hash_password(args.password),
        role="admin",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    print(f"Admin user '{args.username}' created with id={user_id}")


if __name__ == "__main__":
    main()
