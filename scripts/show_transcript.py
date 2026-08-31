from backend.db import get_conn

conn = get_conn()

call_id = '1dcef09fb6374319'  # Jennifer Garcia - transfer $102

call = conn.execute("SELECT customer_name, agent_name, summary FROM calls WHERE call_id = %s", (call_id,)).fetchone()
print(f"{call['customer_name']} → {call['agent_name']}")
print(f"Summary: {call['summary']}\n")

chunks = conn.execute(
    "SELECT chunk_index, text FROM chunks WHERE call_id = %s ORDER BY chunk_index",
    (call_id,)
).fetchall()

print("=== Full transcript chunks ===")
for c in chunks:
    print(f"\n[Chunk {c['chunk_index']}]")
    print(c['text'])
