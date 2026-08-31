import requests

# Batch evaluate the top 20 unevaluated calls via the API
from backend.db import get_conn
conn = get_conn()

# Find calls not yet evaluated, worst attention score first
print("=== Unevaluated calls to try (worst first) ===")
candidates = conn.execute('''
    SELECT c.call_id, c.agent_name, c.customer_name, c.intent,
           c.attention_score, c.ghost_resolved, c.mood_start
    FROM calls c
    WHERE c.processed = 1
      AND c.call_id NOT IN (SELECT DISTINCT call_id FROM rule_violations)
    ORDER BY c.ghost_resolved DESC, c.mood_start DESC
    LIMIT 15
''').fetchall()
for r in candidates:
    ghost = "GHOST" if r['ghost_resolved'] else ""
    print(f"  {r['call_id']} | {r['agent_name']:<12} | attn={r['attention_score']} {ghost} | {r['intent']}")

# Also show any violations already found
print()
print("=== Violations already recorded ===")
rows = conn.execute('''
    SELECT rv.call_id, c.agent_name, c.intent, cr.name as rule_name
    FROM rule_violations rv
    JOIN calls c ON c.call_id = rv.call_id
    JOIN compliance_rules cr ON cr.rule_id = rv.rule_id
    WHERE rv.had_violation = 1
    ORDER BY rv.evaluated_at DESC
''').fetchall()
if not rows:
    print("  None yet")
for r in rows:
    print(f"  call={r['call_id'][:8]} | agent={r['agent_name']} | rule={r['rule_name']}")
