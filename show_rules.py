from backend.db import get_conn
conn = get_conn()
rows = conn.execute('SELECT rule_id, name, description FROM compliance_rules ORDER BY rule_id').fetchall()
for r in rows:
    print(f"{r['rule_id']}: {r['name']}")
    print(f"  {r['description']}")
    print()
