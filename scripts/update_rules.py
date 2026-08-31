from backend.db import get_conn

conn = get_conn()

updates = [
    (
        "RULE_011",
        "Resolution confirmation before ending call",
        "Before ending the call, the agent must ask the customer a direct question confirming their issue is resolved — for example 'Is there anything else I can help you with?' or 'Has your issue been resolved?'. Simply saying 'Have a great day' or 'Thank you for calling' without first asking if the issue is resolved is a violation. Look for a direct question addressed to the customer about whether their need was met.",
    ),
    (
        "RULE_012",
        "Escalation offer for unresolved calls",
        "If the customer's issue was NOT resolved during the call — the customer repeated their request, expressed the problem was not fixed, or the agent failed to complete the requested action — the agent must explicitly offer to escalate to a supervisor or schedule a callback before hanging up. Ending the call without this offer when the issue is unresolved is a violation. Check: did the agent complete the customer's request? If not, did they offer escalation?",
    ),
    (
        "RULE_013",
        "Acknowledgement of customer dissatisfaction",
        "If the customer repeated their request more than once, used words indicating frustration ('still', 'again', 'but I said', 'you misunderstood'), or the transcript shows the customer was dissatisfied, the agent must say something that acknowledges this — for example 'I understand this has been frustrating' or 'I apologise for the confusion'. Simply proceeding or ending the call without acknowledgement is a violation.",
    ),
]

for rule_id, name, description in updates:
    conn.execute(
        'UPDATE compliance_rules SET name = ?, description = ? WHERE rule_id = ?',
        (name, description, rule_id)
    )
    print(f"Updated {rule_id}: {name}")

conn.commit()
print("Done.")
