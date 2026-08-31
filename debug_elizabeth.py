from backend.db import get_conn

conn = get_conn()

# Check all Elizabeth+Robert calls and their violation records
rows = conn.execute(
    "SELECT call_id, customer_name, agent_name FROM calls WHERE customer_name ILIKE %s LIMIT 10",
    ('%Elizabeth%',)
).fetchall()

print("=== All Elizabeth calls ===")
for r in rows:
    call_id = r['call_id']
    viols = conn.execute(
        "SELECT rule_id, had_violation FROM rule_violations WHERE call_id = %s ORDER BY rule_id",
        (call_id,)
    ).fetchall()
    print(f"\n{call_id} | agent={r['agent_name']}")
    if viols:
        for v in viols:
            mark = "VIOLATION" if v['had_violation'] else "passed"
            print(f"  {v['rule_id']}: {mark}")
    else:
        print("  (no records — never evaluated)")

# Also check chunks for the first call to see what closing keywords would match
print("\n\n=== Chunks for 223ca391c70d4e17 containing closing phrases ===")
chunks = conn.execute(
    "SELECT chunk_index, text FROM chunks WHERE call_id = %s ORDER BY chunk_index",
    ('223ca391c70d4e17',)
).fetchall()

CLOSING_KEYWORDS = [
    "thank you for calling", "have a great day", "goodbye",
    "is there anything else", "anything else i can help",
    "have a good", "take care", "bye",
]

for c in chunks:
    text = (c['text'] or '').lower()
    hits = [k for k in CLOSING_KEYWORDS if k in text]
    if hits:
        print(f"\nChunk {c['chunk_index']} hits {hits}:")
        print(f"  {c['text'][:200]}")
