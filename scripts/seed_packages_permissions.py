#!/usr/bin/env python3
"""CLI wrapper for bootstrap seeding (also runs on app startup)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.bootstrap_seed import seed_bootstrap
from database.database import SessionLocal


def run_seed() -> None:
    db = SessionLocal()
    try:
        print("\n=== Starting Database Seeding ===")
        seed_bootstrap(db)
        print("\n=== Database Seeding Completed Successfully ===\n")
    except Exception as e:
        print(f"\n✗ Seed script failed: {e}\n")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
