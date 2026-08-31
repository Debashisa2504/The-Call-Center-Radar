from backend.db import get_conn

conn = get_conn()

new_rules = [
    (
        "RULE_011",
        "Resolution confirmation before ending call",
        "Agent must explicitly confirm with the customer that their issue has been resolved before ending the call. Ending the call while the customer's request is still open or unacknowledged is a violation.",
        "high"
    ),
    (
        "RULE_012",
        "Escalation offer for unresolved calls",
        "If the agent is unable to resolve the customer's issue during the call, the agent must offer to escalate to a supervisor or arrange a callback. Simply ending the call on an unresolved issue without offering escalation is a violation.",
        "high"
    ),
    (
        "RULE_013",
        "Acknowledgement of customer dissatisfaction",
        "If the customer expresses frustration, dissatisfaction, or repeats their request more than once, the agent must explicitly acknowledge the customer's feelings before proceeding or ending the call.",
        "medium"
    ),
]

for rule_id, name, description, severity in new_rules:
    # Check if already exists
    existing = conn.execute('SELECT rule_id FROM compliance_rules WHERE rule_id = ?', (rule_id,)).fetchone()
    if existing:
        print(f"  {rule_id} already exists — skipping")
        continue
    conn.execute(
        'INSERT INTO compliance_rules (rule_id, name, description, severity, enabled) VALUES (?, ?, ?, ?, ?)',
        (rule_id, name, description, severity, 1)
    )
    print(f"  Added {rule_id}: {name}")

conn.commit()
print("Done.")
