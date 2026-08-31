"""
Batch-evaluate compliance on all unevaluated calls.
Runs the full pipeline server-side, then prints any violations found.
"""
import time
import requests
from backend.db import get_conn

API = "http://127.0.0.1:8000"

conn = get_conn()
calls = conn.execute('''
    SELECT c.call_id, c.agent_name, c.intent
    FROM calls c
    WHERE c.processed = 1
      AND c.call_id NOT IN (SELECT DISTINCT call_id FROM rule_violations)
    ORDER BY c.ghost_resolved DESC
    LIMIT 30
''').fetchall()

print(f"Evaluating {len(calls)} calls one at a time...")
for i, c in enumerate(calls):
    cid = c['call_id']
    try:
        r = requests.post(f"{API}/calls/{cid}/compliance/evaluate", timeout=10)
        print(f"  [{i+1}/{len(calls)}] {cid[:8]} {c['agent_name']:<10} → {r.status_code} — waiting 75s...")
        time.sleep(75)  # wait for this call's evaluation to finish before next
    except Exception as e:
        print(f"  [{i+1}/{len(calls)}] {cid[:8]} ERROR: {e}")
        time.sleep(5)

print("\n=== VIOLATIONS FOUND ===")
rows = conn.execute('''
    SELECT rv.call_id, c.agent_name, c.intent, cr.name as rule_name, rv.evidence_json
    FROM rule_violations rv
    JOIN calls c ON c.call_id = rv.call_id
    JOIN compliance_rules cr ON cr.rule_id = rv.rule_id
    WHERE rv.had_violation = 1
    ORDER BY rv.evaluated_at DESC
''').fetchall()

if not rows:
    print("No violations found in this batch.")
for r in rows:
    print(f"\ncall={r['call_id'][:8]} | agent={r['agent_name']} | {r['intent'][:50]}")
    print(f"  RULE: {r['rule_name']}")
    if r['evidence_json']:
        print(f"  EVIDENCE: {str(r['evidence_json'])[:200]}")
