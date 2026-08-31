from backend.db import get_conn

conn = get_conn()

# Find any calls that actually have violations flagged
rows = conn.execute("""
    SELECT rv.call_id, rv.rule_id, c.customer_name, c.agent_name, c.intent,
           cr.name as rule_name, cr.severity
    FROM rule_violations rv
    JOIN calls c ON c.call_id = rv.call_id
    JOIN compliance_rules cr ON cr.rule_id = rv.rule_id
    WHERE rv.had_violation = 1
    ORDER BY cr.severity DESC, rv.call_id
    LIMIT 30
""").fetchall()

if not rows:
    print("No violations found in any evaluated call.")
else:
    print(f"Found {len(rows)} violations across all calls:\n")
    for r in rows:
        print(f"  {r['call_id']} | {r['customer_name']} → {r['agent_name']}")
        print(f"    [{r['severity'].upper()}] {r['rule_id']}: {r['rule_name']}")
        print(f"    Intent: {r['intent']}")
        print()

# Also show how many calls have been evaluated total
total = conn.execute("SELECT COUNT(DISTINCT call_id) as n FROM rule_violations").fetchone()
print(f"Total evaluated calls: {total['n']}")
