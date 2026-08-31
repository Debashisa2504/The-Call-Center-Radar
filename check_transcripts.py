"""
Run this to verify that the 3 test-ingested calls have correct transcripts.
Usage:  python check_transcripts.py
"""
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL", "")
if not DB_URL:
    raise SystemExit("DATABASE_URL not set in .env")

CALL_IDS = [
    "004860b1ab2e4c88",
    "0091a706bc604188",
    "00d676d7058c49bb",
]

conn = psycopg2.connect(DB_URL)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

for cid in CALL_IDS:
    print(f"\n{'='*60}")
    print(f"Call: {cid}")
    print(f"{'='*60}")
    cur.execute(
        "SELECT speaker, start_s, text FROM turns WHERE call_id=%s ORDER BY start_s",
        (cid,),
    )
    rows = cur.fetchall()
    if not rows:
        print("  (no turns found)")
        continue
    for t in rows:
        s = t["start_s"]
        spk = t["speaker"]
        txt = t["text"][:100]
        print(f"  {s:6.1f}s  [{spk:8}]  {txt}")

conn.close()
print("\nDone.")
