from backend.db import get_conn
conn = get_conn()

call_id = '51aec7fcd6894d76'
rows = conn.execute("""
    SELECT rv.rule_id, rv.had_violation, cr.name
    FROM rule_violations rv
    JOIN compliance_rules cr ON rv.rule_id = cr.rule_id
    WHERE rv.call_id = %s
    ORDER BY rv.rule_id
""", (call_id,)).fetchall()
print("Rules stored for this call:")
for r in rows:
    print(f"  {r['rule_id']}  had_violation={r['had_violation']}  {r['name']}")

print()
all_rules = conn.execute("SELECT rule_id, name FROM compliance_rules WHERE enabled=1 ORDER BY rule_id").fetchall()
print("All enabled rules:", [r['rule_id'] for r in all_rules])
missing = set(r['rule_id'] for r in all_rules) - set(r['rule_id'] for r in rows)
print("Missing rules:", sorted(missing))
