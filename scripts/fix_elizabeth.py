from backend.db import get_conn

conn = get_conn()

rows = conn.execute(
    "SELECT call_id FROM calls WHERE customer_name ILIKE %s AND agent_name ILIKE %s LIMIT 5",
    ('%Elizabeth%', '%Robert%')
).fetchall()

print("Matching calls:")
for r in rows:
    print(f"  {r['call_id']}")

if rows:
    call_id = rows[0]['call_id']
    deleted = conn.execute(
        "DELETE FROM rule_violations WHERE call_id = %s",
        (call_id,)
    ).rowcount
    print(f"\nDeleted {deleted} old violation records for {call_id}")
    print("Now restart the backend and re-evaluate this call in the UI.")
else:
    print("No matching call found.")
