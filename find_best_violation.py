from backend.db import get_conn

conn = get_conn()

# Show all rules
print("=== All compliance rules ===")
rules = conn.execute("SELECT rule_id, name, description, severity FROM compliance_rules ORDER BY rule_id").fetchall()
for r in rules:
    print(f"\n{r['rule_id']} [{r['severity']}]: {r['name']}")
    print(f"  {r['description'][:200]}")

# Find ghost-resolved calls (clearest violations - agent falsely claimed resolution)
print("\n\n=== Ghost-resolved calls (agent falsely claimed resolved) ===")
ghosts = conn.execute("""
    SELECT c.call_id, c.customer_name, c.agent_name, c.ghost_gap_min, c.summary
    FROM calls c
    WHERE c.ghost_resolved = 1
      AND c.processed = 1
      AND c.call_id NOT IN (SELECT DISTINCT call_id FROM rule_violations)
    ORDER BY c.ghost_gap_min ASC
    LIMIT 10
""").fetchall()

for g in ghosts:
    print(f"\n{g['call_id']} | {g['customer_name']} → {g['agent_name']} | callback in {g['ghost_gap_min']:.1f} min")
    print(f"  {g['summary'][:150]}")

# Find calls where attention_score is high AND unresolved AND never evaluated
print("\n\n=== High attention + unresolved + unevaluated ===")
highattn = conn.execute("""
    SELECT c.call_id, c.customer_name, c.agent_name, c.attention_score, c.intent, c.attention_reason
    FROM calls c
    WHERE c.attention_score >= 80
      AND c.transcript_resolved = 0
      AND c.call_id NOT IN (SELECT DISTINCT call_id FROM rule_violations)
    ORDER BY c.attention_score DESC
    LIMIT 5
""").fetchall()

for h in highattn:
    print(f"\n{h['call_id']} | {h['customer_name']} → {h['agent_name']} | score={h['attention_score']}")
    print(f"  Intent: {h['intent']}")
    print(f"  Reason: {h['attention_reason']}")
