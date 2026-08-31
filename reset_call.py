from backend.db import get_conn

conn = get_conn()
call_id = '533aa9f57d9448e5'

deleted = conn.execute(
    "DELETE FROM rule_violations WHERE call_id = %s",
    (call_id,)
).rowcount

print(f"Deleted {deleted} violation records for {call_id}")
print("Now click 'Evaluate 13 rules' in the UI for Elizabeth Brown's call.")
