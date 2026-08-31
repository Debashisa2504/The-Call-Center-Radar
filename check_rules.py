from backend.db import get_conn
conn = get_conn()
rows = conn.execute("SELECT rule_id, name, enabled FROM compliance_rules ORDER BY rule_id").fetchall()
for r in rows:
    print(f"{r['rule_id']}: enabled={r['enabled']}  {r['name']}")
print(f"\nTotal: {len(rows)}")
