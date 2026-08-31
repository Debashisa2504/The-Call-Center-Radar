from backend.db import get_conn

conn = get_conn()

conn.execute(
    "UPDATE compliance_rules SET description = %s WHERE rule_id = %s",
    (
        "When a customer requests a fund transfer or any payment instruction, "
        "the agent MUST read a fraud awareness disclosure before asking for any "
        "account details or processing the request. The disclosure must warn the "
        "customer about impersonation scams. If the transcript shows the agent "
        "asking for transfer details (amount, source account, destination account) "
        "OR confirming a transfer, without ANY prior mention of fraud, scams, "
        "impersonation, or a disclosure — that is a violation. Do not assume the "
        "disclosure happened off-transcript.",
        "RULE_003"
    )
)
print("Updated RULE_003")

# Also delete any existing evaluations for the Jennifer Garcia transfer call
# so it gets re-evaluated with the new prompt
call_id = '1dcef09fb6374319'
deleted = conn.execute("DELETE FROM rule_violations WHERE call_id = %s", (call_id,)).rowcount
print(f"Cleared {deleted} old records for {call_id}")

# Also clear the completed $69 transfer call (Michael Williams)
# to give another clean violation candidate
call_id2 = None
row = conn.execute(
    "SELECT call_id FROM calls WHERE customer_name ILIKE %s AND intent ILIKE %s AND transcript_resolved = 1 LIMIT 1",
    ('%Michael%', '%transfer%')
).fetchone()
if row:
    call_id2 = row['call_id']
    deleted2 = conn.execute("DELETE FROM rule_violations WHERE call_id = %s", (call_id2,)).rowcount
    print(f"Cleared {deleted2} old records for {call_id2} (Michael Williams transfer)")
