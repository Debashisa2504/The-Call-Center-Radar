from backend.db import get_conn

conn = get_conn()

# Remove any existing RULE_014
conn.execute("DELETE FROM compliance_rules WHERE rule_id = 'RULE_014'")

conn.execute(
    "INSERT INTO compliance_rules (rule_id, name, description, severity, enabled) VALUES (%s, %s, %s, %s, %s)",
    (
        "RULE_014",
        "No repeated requests for already-provided information",
        (
            "The agent must NOT ask the customer to repeat or re-confirm information "
            "the customer has already clearly stated during the same call. "
            "For example: if the customer says 'I want to transfer $102 from my savings to my checking account' "
            "and the agent then asks 'What is the source account?' or 'What is the destination account?' "
            "— that is a violation. Similarly, if the customer provides a date and time for an appointment "
            "and the agent asks 'What time would you like?' — that is a violation. "
            "Look for the agent requesting information the customer already stated. "
            "This is a violation even if the agent says 'Can you repeat that?' or 'What is your X?' "
            "when the customer already answered it moments earlier."
        ),
        "high",
        1
    )
)
print("Added RULE_014: No repeated requests for already-provided information")

# Clear Jennifer Garcia's transfer call so it re-evaluates
call_id = '1dcef09fb6374319'
deleted = conn.execute("DELETE FROM rule_violations WHERE call_id = %s", (call_id,)).rowcount
print(f"Cleared {deleted} old records for {call_id}")

# Also clear Elizabeth Brown's appointment call
call_id2 = '533aa9f57d9448e5'
deleted2 = conn.execute("DELETE FROM rule_violations WHERE call_id = %s", (call_id2,)).rowcount
print(f"Cleared {deleted2} old records for {call_id2} (Elizabeth Brown)")

conn.commit()
print("Committed.")
