from backend.db import get_conn

conn = get_conn()

# Find by name + intent
rows = conn.execute(
    "SELECT call_id, customer_name, agent_name, intent FROM calls WHERE customer_name ILIKE %s AND intent ILIKE %s LIMIT 10",
    ('%Elizabeth%', '%appointment%')
).fetchall()

print("=== Elizabeth + appointment calls ===")
for r in rows:
    call_id = r['call_id']
    print(f"\n{call_id} | customer={r['customer_name']} | agent={r['agent_name']}")
    print(f"  Intent: {r['intent']}")
    viols = conn.execute(
        "SELECT rule_id, had_violation FROM rule_violations WHERE call_id = %s ORDER BY rule_id",
        (call_id,)
    ).fetchall()
    if viols:
        for v in viols:
            mark = "VIOLATION" if v['had_violation'] else "passed"
            print(f"    {v['rule_id']}: {mark}")
    else:
        print("    (no records — never evaluated)")

    # Check keyword hits in chunks
    chunks = conn.execute(
        "SELECT chunk_index, text FROM chunks WHERE call_id = %s ORDER BY chunk_index",
        (call_id,)
    ).fetchall()
    CLOSING_KEYWORDS = ["thank you for calling", "have a great day", "goodbye",
                        "is there anything else", "anything else i can help", "bye"]
    for c in chunks:
        text = (c['text'] or '').lower()
        hits = [k for k in CLOSING_KEYWORDS if k in text]
        if hits:
            print(f"    Chunk {c['chunk_index']} keyword hits: {hits}")
