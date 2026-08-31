"""
Run this once to create all tables + pgvector extension in the target database.
Usage:  python init_schema.py
"""
import os
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL", "")
if not DB_URL:
    raise SystemExit("DATABASE_URL not set in .env — point it to callradar_v2 first")

print(f"Initializing schema on: {DB_URL.split('@')[-1]}")  # print host only, not creds

from backend.db import init_db
init_db()
print("Schema ready.")
