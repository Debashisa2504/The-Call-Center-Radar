from backend.db import get_conn
conn = get_conn()

# Find unresolved calls or calls with mood shift down and negative summary
rows = conn.execute("""
    SELECT call_id, customer_name, agent_name, intent, summary, mood_start, transcript_resolved, ghost_resolved
    FROM calls
    WHERE processed = 1
      AND (
          transcript_resolved = 0
          OR summary ILIKE '%%dissatisf%%'
          OR summary ILIKE '%%unresolved%%'
          OR summary ILIKE '%%misunderstand%%'
          OR summary ILIKE '%%not addressed%%'
          OR summary ILIKE '%%incorrectly%%'
          OR summary ILIKE '%%frustrat%%'
      )
    ORDER BY ghost_resolved DESC, transcript_resolved ASC
    LIMIT 20
""").fetchall()

for r in rows:
    ghost = "GHOST" if r['ghost_resolved'] else ""
    resolved = "resolved" if r['transcript_resolved'] else "UNRESOLVED"
    print(f"\n{r['call_id']}")
    print(f"  {r['customer_name']} → {r['agent_name']} | {resolved} {ghost}")
    print(f"  Intent: {r['intent']}")
    print(f"  Summary: {r['summary']}")
