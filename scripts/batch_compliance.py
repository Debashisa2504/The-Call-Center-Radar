"""
Batch compliance evaluation across all 1400 calls.
Runs deterministic rules only (no GPT API calls) so it is fast and free.
Usage:
    python batch_compliance.py              # evaluate all unevaluated calls
    python batch_compliance.py --all        # re-evaluate every call (clears old results)
    python batch_compliance.py --limit 100  # evaluate first 100 unevaluated calls
    python batch_compliance.py --summary    # just print violation summary, no evaluation
"""
import sys
import time
from collections import defaultdict
from backend.db import get_conn
from backend.pipeline.compliance import evaluate_call_compliance

args = sys.argv[1:]
re_evaluate_all = "--all" in args
summary_only    = "--summary" in args
limit = None
if "--limit" in args:
    idx = args.index("--limit")
    limit = int(args[idx + 1])

conn = get_conn()

if summary_only:
    print("=== Compliance Violation Summary ===\n")
    rows = conn.execute("""
        SELECT cr.rule_id, cr.name, cr.severity,
               COUNT(*) FILTER (WHERE rv.had_violation = 1) as violations,
               COUNT(*) as evaluated
        FROM compliance_rules cr
        LEFT JOIN rule_violations rv ON rv.rule_id = cr.rule_id
        WHERE cr.enabled = 1
        GROUP BY cr.rule_id, cr.name, cr.severity
        ORDER BY violations DESC
    """).fetchall()
    for r in rows:
        bar = "#" * r["violations"]
        print(f"  {r['rule_id']} [{r['severity']:8}] {r['name'][:45]:<45} "
              f"| {r['violations']:>4} violations / {r['evaluated']:>4} evaluated  {bar}")

    print("\n=== Most Violated Calls ===\n")
    calls = conn.execute("""
        SELECT c.call_id, c.customer_name, c.agent_name,
               COUNT(*) FILTER (WHERE rv.had_violation = 1) as viol_count
        FROM calls c
        JOIN rule_violations rv ON rv.call_id = c.call_id
        WHERE rv.had_violation = 1
        GROUP BY c.call_id, c.customer_name, c.agent_name
        ORDER BY viol_count DESC
        LIMIT 20
    """).fetchall()
    for c in calls:
        print(f"  {c['call_id']} | {c['customer_name']} -> {c['agent_name']} | {c['viol_count']} violations")
    sys.exit(0)

# Find calls to evaluate
if re_evaluate_all:
    query = "SELECT call_id FROM calls WHERE processed = 1 ORDER BY call_id"
    print("Mode: re-evaluate ALL calls (clears existing results)")
else:
    query = """
        SELECT call_id FROM calls
        WHERE processed = 1
          AND call_id NOT IN (SELECT DISTINCT call_id FROM rule_violations)
        ORDER BY call_id
    """
    print("Mode: evaluate unevaluated calls only")

calls = conn.execute(query).fetchall()
if limit:
    calls = calls[:limit]

total = len(calls)
print(f"Found {total} calls to evaluate\n")

violations_by_rule = defaultdict(int)
total_violations   = 0
errors             = 0

for i, row in enumerate(calls, 1):
    call_id = row["call_id"]
    try:
        result = evaluate_call_compliance(call_id)
        viols  = [r for r in result if isinstance(r, dict) and r.get("rule_id")] if isinstance(result, list) else []
        v_count = len(viols)
        for v in viols:
            violations_by_rule[v.get("rule_id", "?")] += 1
        total_violations += v_count
        status = f"  {v_count} violation(s): {', '.join(v.get('rule_id','?') for v in viols)}" if v_count else "  clean"
        print(f"[{i:>4}/{total}] {call_id} {status}")
    except Exception as e:
        errors += 1
        print(f"[{i:>4}/{total}] {call_id}  ERROR: {e}")

print(f"\n=== Done ===")
print(f"Evaluated: {total}  |  Total violations: {total_violations}  |  Errors: {errors}")
print("\nViolations by rule:")
for rule_id, count in sorted(violations_by_rule.items()):
    print(f"  {rule_id}: {count}")
