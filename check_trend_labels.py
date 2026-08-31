from backend.db import get_conn
conn = get_conn()

# Check what trend_label values exist
rows = conn.execute("""
    SELECT trend_label, COUNT(*) as cnt
    FROM calls
    WHERE trend_label IS NOT NULL AND trend_label != ''
    GROUP BY trend_label
    ORDER BY cnt DESC
    LIMIT 20
""").fetchall()

print("=== trend_label distribution ===")
for r in rows:
    print(f"  [{r['cnt']:>4}] {repr(r['trend_label'])}")

# Check a sample of the blank-topic ones
print("\n=== Sample calls with bare 'Little Harper Valley 1:' label ===")
samples = conn.execute("""
    SELECT call_id, trend_label, intent
    FROM calls
    WHERE trend_label = 'Little Harper Valley 1:'
       OR trend_label LIKE '%: '
       OR (trend_label IS NOT NULL AND trend_label NOT LIKE "%'%")
    LIMIT 5
""").fetchall()
for s in samples:
    print(f"  {s['call_id']}: trend_label={repr(s['trend_label'])} | intent={s['intent'][:60]}")
