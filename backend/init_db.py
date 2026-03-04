#!/usr/bin/env python3
"""One-time script to create all database tables."""
import sys
import os

# Run from backend/ directory
sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine, Base
from app import models  # noqa: F401 — registers all ORM classes


def main():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Done. Tables created:")
    for table_name in Base.metadata.tables:
        print(f"  - {table_name}")


if __name__ == "__main__":
    main()
