"""
backend/main.py
================
FastAPI REST server -- all endpoints read from PostgreSQL.
Audio streamed from disk for the playable recording UI.

New endpoints added for improvements
--------------------------------------
GET  /calls/{id}/compliance          Compliance violation results for a call
POST /calls/{id}/compliance/evaluate Trigger on-demand rule evaluation
GET  /calls/{id}/suggestions         Follow-up question suggestions
GET  /dashboard/compliance           Compliance summary across all calls
GET  /compliance/rules               List all compliance rules
POST /compliance/rules               Create a custom compliance rule
GET  /dashboard/sentiment            Emotion distribution across agents
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import CORS_ORIGINS, API_HOST, API_PORT, AUDIO_DIR
from .db import db, init_db
from .pipeline.ghost import get_agent_ghost_rates, compute_customer_trajectories


def _row(r) -> dict:
    """Convert a DB row to plain dict, coercing Decimal float for JSON."""
    from decimal import Decimal
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in dict(r).items()}
from .pipeline.compliance import (
    seed_default_rules, evaluate_call_compliance,
    get_call_violations, get_compliance_summary,
)
from .pipeline.suggestions import generate_call_suggestions

app = FastAPI(
    title="Call Radar API",
    description="Grounded call-centre intelligence: ghost resolution + 7-emotion sentiment + compliance.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    import threading
    init_db()
    seed_default_rules()
    from .pipeline.ghost import compute_ghost_resolutions
    t = threading.Thread(target=compute_ghost_resolutions, daemon=True)
    t.start()


#  "EUR "EUR Health  "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR

@app.get("/")
def root():
    with db() as conn:
        total  = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
        done   = conn.execute("SELECT COUNT(*) FROM calls WHERE processed=1").fetchone()[0]
        ghosts = conn.execute("SELECT COUNT(*) FROM calls WHERE ghost_resolved=1").fetchone()[0]
        violations = conn.execute(
            "SELECT COUNT(*) FROM rule_violations WHERE had_violation=1"
        ).fetchone()[0]
    return {
        "service":            "call-radar-api",
        "version":            "2.0.0",
        "total_calls":        total,
        "processed_calls":    done,
        "ghost_resolutions":  ghosts,
        "ghost_rate_pct":     round(ghosts / done * 100, 1) if done else 0,
        "compliance_violations": violations,
    }


@app.get("/health")
def health():
    with db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM calls WHERE processed=1"
        ).fetchone()[0]
    return {"status": "ready" if count > 0 else "empty", "processed_calls": count}


#  "EUR "EUR Single call  "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR

@app.get("/calls/{call_id}")
def get_call(call_id: str):
    """
    Full call detail: transcript, 7-emotion sentiment, intent, mood shift,
    dual resolution signals, ghost status, attention score, all evidence.
    """
    with db() as conn:
        call = conn.execute(
            "SELECT * FROM calls WHERE call_id=?", (call_id,)
        ).fetchone()
        if not call:
            raise HTTPException(404, "Call not found")

        turns = conn.execute(
            "SELECT speaker, start_s, end_s, text FROM turns "
            "WHERE call_id=? ORDER BY start_s", (call_id,)
        ).fetchall()

        evidence = conn.execute(
            "SELECT judgment_type, timestamp_s, quote, reasoning "
            "FROM evidence WHERE call_id=? ORDER BY timestamp_s", (call_id,)
        ).fetchall()

    # Parse stored JSON sentiment fields
    def safe_json(s):
        if not s: return {}
        try: return json.loads(s)
        except: return {}

    return {
        "call_id":           call["call_id"],
        "customer_name":     call["customer_name"],
        "agent_name":        call["agent_name"],
        "start_time_ms":     call["start_time_ms"],
        "duration_s":        call["duration_s"],
        "session":           call["session"],
        "audio_url":         f"/audio/{call_id}",
        # Core analysis
        "intent":            call["intent"],
        "mood_start":        call["mood_start"],
        "mood_shift":        bool(call["mood_shift"]),
        "mood_shift_time_s": call["mood_shift_time_s"],
        "mood_shift_quote":  call["mood_shift_quote"],
        "mood_shift_direction": call["mood_shift_direction"],
        # Dual resolution signals
        "transcript_resolved":  bool(call["transcript_resolved"]),
        "behavioural_resolved": bool(call["behavioural_resolved"]),
        "ghost_resolved":       bool(call["ghost_resolved"]),
        "ghost_gap_min":        call["ghost_gap_min"],
        "ghost_callback_id":    call["ghost_callback_id"],
        # Summary + attention
        "summary":           call["summary"],
        "attention_score":   call["attention_score"],
        "attention_reason":  call["attention_reason"],
        # 7-emotion sentiment (CortexV improvement)
        "sentiment": {
            "overall": {
                "score":   call["sentiment_score"],
                "label":   call["sentiment_label"],
                "summary": call["sentiment_summary"],
            },
            "agent":    safe_json(call["agent_sentiment_json"]),
            "customer": safe_json(call["customer_sentiment_json"]),
        },
        "dominant_emotion":  call["dominant_emotion"],
        "emotion_scores":    safe_json(call["emotion_scores_json"]),
        # Quality signals
        "caller_mos":        call["caller_mos"],
        "agent_mos":         call["agent_mos"],
        "partner_rating":    call["partner_rating"],
        # Trend
        "trend_label":       call["trend_label"],
        # Transcript
        "transcript": [_row(t) for t in turns],
        # Evidence
        "evidence": [_row(e) for e in evidence],
    }


@app.get("/audio/{call_id}")
def get_audio(call_id: str):
    """Stream the MP3 for the playable recording."""
    path = AUDIO_DIR / f"{call_id}.mp3"
    if not path.exists():
        raise HTTPException(404, "Audio not found")
    return FileResponse(str(path), media_type="audio/mpeg")


@app.get("/calls/{call_id}/compliance")
def call_compliance(call_id: str):
    """Return all compliance rule evaluation results for this call."""
    with db() as conn:
        exists = conn.execute(
            "SELECT call_id FROM calls WHERE call_id=?", (call_id,)
        ).fetchone()
    if not exists:
        raise HTTPException(404, "Call not found")
    return get_call_violations(call_id)


_eval_semaphore = asyncio.Semaphore(1)  # only 1 compliance eval at a time


@app.post("/calls/{call_id}/compliance/evaluate")
async def evaluate_compliance(call_id: str, background_tasks: BackgroundTasks):
    """
    Trigger on-demand compliance rule evaluation for a specific call.
    Runs in a background task - returns immediately.
    Poll GET /calls/{id}/compliance for results.
    Semaphore limits to 1 concurrent evaluation to prevent uvicorn overload.
    """
    with db() as conn:
        exists = conn.execute(
            "SELECT call_id FROM calls WHERE call_id=%s", (call_id,)
        ).fetchone()
    if not exists:
        raise HTTPException(404, "Call not found")

    async def _guarded():
        async with _eval_semaphore:
            await asyncio.get_event_loop().run_in_executor(
                None, evaluate_call_compliance, call_id
            )

    background_tasks.add_task(_guarded)
    return {"status": "evaluating", "call_id": call_id,
            "message": "Poll GET /calls/{call_id}/compliance for results"}


@app.get("/compliance/rules")
def list_rules():
    """List all compliance rules."""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM compliance_rules ORDER BY rule_id"
        ).fetchall()
    return [_row(r) for r in rows]


class RuleCreate(BaseModel):
    name:        str
    description: str
    severity:    str = "medium"


@app.post("/compliance/rules")
def create_rule(rule: RuleCreate):
    """Create a custom compliance rule."""
    import uuid
    rule_id = f"CUSTOM_{uuid.uuid4().hex[:8].upper()}"
    now     = datetime.utcnow().isoformat()
    with db() as conn:
        conn.execute("""
            INSERT INTO compliance_rules (rule_id, name, description, severity, enabled, created_at)
            VALUES (?,?,?,?,1,?)
        """, (rule_id, rule.name, rule.description, rule.severity, now))
    return {"rule_id": rule_id, "status": "created"}


@app.get("/dashboard/compliance")
def compliance_dashboard():
    """Aggregate compliance statistics across all calls."""
    return get_compliance_summary()


#  "EUR "EUR Follow-up suggestions  "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR

@app.get("/calls/{call_id}/suggestions")
def call_suggestions(call_id: str):
    """Generate 3 contextual follow-up questions for a call detail view."""
    with db() as conn:
        call = conn.execute(
            "SELECT customer_name, agent_name, intent, summary, "
            "ghost_resolved, ghost_gap_min, attention_reason "
            "FROM calls WHERE call_id=?", (call_id,)
        ).fetchone()
    if not call:
        raise HTTPException(404, "Call not found")

    suggestions = generate_call_suggestions(
        intent=call["intent"] or "",
        summary=call["summary"] or "",
        agent_name=call["agent_name"],
        customer_name=call["customer_name"],
        ghost_resolved=bool(call["ghost_resolved"]),
        ghost_gap_min=call["ghost_gap_min"],
        attention_reason=call["attention_reason"] or "",
    )
    return {"suggestions": suggestions}


#  "EUR "EUR Sentiment dashboard  "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR

@app.get("/dashboard/sentiment")
def sentiment_dashboard():
    """
    Aggregate emotion distribution per agent across all calls.
    Used by the agent performance view to show emotional engagement patterns.
    """
    with db() as conn:
        rows = conn.execute("""
            SELECT agent_name,
                   AVG(sentiment_score) as avg_sentiment_score,
                   COUNT(*) as total_calls,
                   SUM(CASE WHEN dominant_emotion='frustrated' THEN 1 ELSE 0 END) as frustrated_calls,
                   SUM(CASE WHEN dominant_emotion='angry'      THEN 1 ELSE 0 END) as angry_calls,
                   SUM(CASE WHEN dominant_emotion='anxious'    THEN 1 ELSE 0 END) as anxious_calls,
                   SUM(CASE WHEN dominant_emotion='engaged'    THEN 1 ELSE 0 END) as engaged_calls,
                   SUM(CASE WHEN dominant_emotion='satisfied' OR dominant_emotion='happy' THEN 1 ELSE 0 END) as positive_calls
            FROM calls WHERE processed=1
            GROUP BY agent_name
            ORDER BY avg_sentiment_score ASC
        """).fetchall()
    return [_row(r) for r in rows]


#  "EUR "EUR Customer views  "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR

@app.get("/customers")
def list_customers(
    search:  Optional[str] = None,
    sort_by: str            = "ghost_rate",
    limit:   int            = 100000,
):
    with db() as conn:
        rows = conn.execute("""
            SELECT
                customer_name,
                COUNT(*) as total_calls,
                SUM(ghost_resolved) as ghost_calls,
                ROUND(AVG(CAST(ghost_resolved AS REAL))::numeric*100,1) as ghost_rate_pct,
                ROUND(AVG(CAST(behavioural_resolved AS REAL))::numeric*100,1) as true_resolution_pct,
                ROUND(AVG(attention_score)::numeric,1) as avg_attention,
                ROUND(AVG(sentiment_score)::numeric,3) as avg_sentiment_score,
                MAX(start_time_ms) as last_call_ms,
                STRING_AGG(DISTINCT agent_name, ', ') as agents,
                STRING_AGG(DISTINCT trend_label, ', ') as issues
            FROM calls WHERE processed=1
            GROUP BY customer_name
            ORDER BY ghost_rate_pct DESC
        """).fetchall()

    customers = [_row(r) for r in rows]
    if search:
        s = search.lower()
        customers = [c for c in customers if s in c["customer_name"].lower()]

    sort_map = {
        "ghost_rate":    lambda x: -(x["ghost_rate_pct"] or 0),
        "total_calls":   lambda x: -x["total_calls"],
        "avg_attention": lambda x: -(x["avg_attention"] or 0),
        "name":          lambda x: x["customer_name"],
    }
    customers.sort(key=sort_map.get(sort_by, sort_map["ghost_rate"]))
    return customers[:limit]


@app.get("/customers/{customer_name}/calls")
def get_customer_calls(customer_name: str):
    with db() as conn:
        rows = conn.execute("""
            SELECT call_id, agent_name, start_time_ms, duration_s,
                   intent, mood_start, mood_shift, mood_shift_direction,
                   transcript_resolved, behavioural_resolved, ghost_resolved,
                   ghost_gap_min, ghost_callback_id,
                   summary, attention_score, trend_label, partner_rating,
                   sentiment_score, dominant_emotion
            FROM calls
            WHERE customer_name=? AND processed=1
            ORDER BY start_time_ms
        """, (customer_name,)).fetchall()

    if not rows:
        raise HTTPException(404, "Customer not found")

    calls = [_row(r) for r in rows]
    for c in calls:
        c["audio_url"]           = f"/audio/{c['call_id']}"
        c["ghost_resolved"]      = bool(c["ghost_resolved"])
        c["transcript_resolved"] = bool(c["transcript_resolved"])
        c["behavioural_resolved"]= bool(c["behavioural_resolved"])
        c["mood_shift"]          = bool(c["mood_shift"])

    mood_score = {"satisfied":5,"calm":4,"confused":3,"frustrated":2,"angry":1}
    moods      = [mood_score.get(c["mood_start"], 3) for c in calls]
    trend      = "stable"
    if len(moods) >= 2:
        if moods[-1] < moods[0] - 0.5:   trend = "deteriorating"
        elif moods[-1] > moods[0] + 0.5: trend = "improving"

    ghost_rate = sum(1 for c in calls if c["ghost_resolved"]) / len(calls) * 100

    return {
        "customer_name":   customer_name,
        "total_calls":     len(calls),
        "ghost_rate_pct":  round(ghost_rate, 1),
        "mood_trajectory": trend,
        "calls":           calls,
    }


#  "EUR "EUR Dashboard views  "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR

@app.get("/dashboard/attention")
def attention_queue(limit: int = 50, ghost_only: bool = False, min_score: int = 75):
    """
    Ranked "needs a manager's attention today" queue.

    Ghost-resolved calls get a boost based on how the callback played out.
    sequence_resolved (set by compute_ghost_resolutions()) tells us whether
    the customer's callback call actually closed the loop:
      - ghost, and STILL unresolved after the callback  -> full +30 boost,
        AND forces the call into the queue unconditionally (this is the
        real failure case — the issue was never actually fixed).
      - ghost, callback resolved it, but took >= 2 min   -> +15 boost only.
      - ghost, callback resolved it in under 2 min        -> +5 boost only.

    Fix: previously, ANY ghost that wasn't "resolved in under 2 minutes"
    was force-included regardless of sequence_resolved — so a ghost that
    took, say, 5 minutes to resolve on callback still forced its way in
    even though the issue was genuinely fixed. Only genuinely-unresolved
    ghosts (sequence_resolved=0) now force membership; resolved-on-callback
    ghosts (fast or slow) are scored via the boost above and only appear
    if attention_score + boost earns them a place.
    """
    ghost_filter = "AND c.ghost_resolved=1" if ghost_only else ""
    with db() as conn:
        rows = conn.execute(f"""
            SELECT c.call_id, c.customer_name, c.agent_name,
                   c.start_time_ms, c.duration_s,
                   c.intent, c.summary, c.attention_score, c.attention_reason,
                   c.mood_start, c.mood_shift, c.mood_shift_direction,
                   c.transcript_resolved, c.behavioural_resolved,
                   c.ghost_resolved, c.ghost_gap_min, c.ghost_callback_id,
                   c.sequence_resolved,
                   c.trend_label, c.sentiment_score, c.dominant_emotion,
                   COALESCE(v.violation_count, 0) as violation_count,
                   (c.attention_score
                    + CASE
                        -- Explicitly unresolved after callback = real failure → +30
                        WHEN c.ghost_resolved = 1 AND c.sequence_resolved = 0 THEN 30
                        -- Resolved on callback but took >= 2 min → modest boost
                        WHEN c.ghost_resolved = 1 AND c.sequence_resolved = 1
                             AND COALESCE(c.ghost_gap_min, 999) >= 2 THEN 15
                        -- Resolved quickly on callback → small boost only
                        WHEN c.ghost_resolved = 1 AND c.sequence_resolved = 1 THEN 5
                        -- NULL = not yet computed; no boost, score on own merit
                        ELSE 0
                      END
                    + LEAST(COALESCE(v.violation_count, 0) * 10, 30)
                   ) AS effective_score
            FROM calls c
            LEFT JOIN (
                SELECT call_id, COUNT(*) as violation_count
                FROM rule_violations
                WHERE had_violation = 1
                GROUP BY call_id
            ) v ON v.call_id = c.call_id
            WHERE c.processed = 1 {ghost_filter}
              -- Only force into queue if explicitly sequence_resolved=0 (not NULL)
              AND (c.attention_score >= ?
                   OR (c.ghost_resolved = 1 AND c.sequence_resolved = 0))
            ORDER BY effective_score DESC
            LIMIT ?
        """, (min_score, limit)).fetchall()
    return [_row(r) for r in rows]


@app.get("/dashboard/ghost-queue")
def ghost_queue(limit: int = 50, unresolved_only: bool = True):
    """
    Calls where the agent claimed resolution but the customer called back.

    Fix: previously this returned EVERY ghost_resolved=1 call with no
    filter on sequence_resolved, so calls where the callback genuinely
    closed the loop sat next to real unresolved failures — the false-flag
    problem. By default (unresolved_only=True) this now only returns
    ghosts where the callback did NOT actually fix the issue — the real
    failures a manager should look at. Pass unresolved_only=false to see
    ghosts that were resolved on callback (for audit / trend purposes).
    """
    # Only show explicitly unresolved ghosts (sequence_resolved = 0).
    # NULL means not yet computed — treat as unknown, not as a failure,
    # to avoid false flags before re-ingestion has set the value.
    resolved_filter = (
        "AND c.sequence_resolved = 0"
        if unresolved_only else ""
    )
    with db() as conn:
        rows = conn.execute(f"""
            SELECT c.call_id, c.customer_name, c.agent_name,
                   c.start_time_ms, c.duration_s,
                   c.intent, c.summary, c.attention_score,
                   c.ghost_gap_min, c.ghost_callback_id,
                   c.sequence_resolved,
                   c.mood_start, c.transcript_resolved,
                   c.dominant_emotion,
                   cb.call_id as next_call_id,
                   cb.agent_name as next_agent_name,
                   cb.intent as next_intent
            FROM calls c
            LEFT JOIN calls cb ON c.ghost_callback_id = cb.call_id
            WHERE c.ghost_resolved=1 {resolved_filter}
            ORDER BY c.ghost_gap_min ASC NULLS LAST
            LIMIT ?
        """, (limit,)).fetchall()
    return [_row(r) for r in rows]


@app.get("/dashboard/trends")
def issue_trends():
    with db() as conn:
        clusters = conn.execute("""
            SELECT t.cluster_id, t.label, t.call_count, t.example_intents,
                   c.ghost_rate, c.avg_attention
            FROM trends t
            LEFT JOIN (
                SELECT trend_cluster,
                       AVG(CAST(ghost_resolved AS REAL)) as ghost_rate,
                       AVG(attention_score) as avg_attention
                FROM calls GROUP BY trend_cluster
            ) c ON t.cluster_id = c.trend_cluster
            ORDER BY t.call_count DESC
        """).fetchall()
        sessions = conn.execute("""
            SELECT session, trend_label, COUNT(*) as count
            FROM calls WHERE processed=1
            GROUP BY session, trend_label
            ORDER BY session, count DESC
        """).fetchall()
    return {
        "clusters":   [dict(r) for r in clusters],
        "by_session": [dict(r) for r in sessions],
    }


@app.get("/dashboard/agents")
def agent_dashboard():
    return get_agent_ghost_rates()


@app.get("/dashboard/customer-trajectories")
def customer_trajectories(limit: int = 20):
    return compute_customer_trajectories()[:limit]


@app.get("/dashboard/stats")
def overall_stats():
    with db() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) as total_calls,
                SUM(ghost_resolved) as ghost_calls,
                ROUND(AVG(CAST(ghost_resolved AS REAL))::numeric*100,1) as ghost_rate_pct,
                ROUND(AVG(CAST(behavioural_resolved AS REAL))::numeric*100,1) as true_resolution_pct,
                ROUND(AVG(CAST(transcript_resolved AS REAL))::numeric*100,1) as claimed_resolution_pct,
                ROUND(AVG(duration_s)::numeric,1) as avg_duration_s,
                ROUND(AVG(attention_score)::numeric,1) as avg_attention_score,
                ROUND(AVG(sentiment_score)::numeric,3) as avg_sentiment_score,
                COUNT(DISTINCT customer_name) as unique_customers,
                COUNT(DISTINCT agent_name) as unique_agents
            FROM calls WHERE processed=1
        """).fetchone()
        violations = conn.execute(
            "SELECT COUNT(*) FROM rule_violations WHERE had_violation=1"
        ).fetchone()[0]
    d = dict(row)
    d["total_compliance_violations"] = violations
    return d


#  "EUR "EUR Customer Perception Dashboard  "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR "EUR

from datetime import timedelta, timezone

def _period_filter(from_date: str = None, to_date: str = None) -> str:
    """Return a SQL WHERE fragment filtering by start_time_ms (epoch ms)."""
    from datetime import datetime, timezone
    parts = []
    if from_date:
        try:
            dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            parts.append(f"AND start_time_ms >= {int(dt.timestamp() * 1000)}")
        except ValueError:
            pass
    if to_date:
        try:
            from datetime import timedelta
            dt = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            parts.append(f"AND start_time_ms < {int(dt.timestamp() * 1000)}")
        except ValueError:
            pass
    return " ".join(parts)


@app.get("/dashboard/issues")
def issue_frequency(from_date: str = None, to_date: str = None, limit: int = 15):
    """Most frequent customer issues with ghost/resolution rates."""
    filter_sql = _period_filter(from_date, to_date)
    with db() as conn:
        rows = conn.execute(f"""
            SELECT
                intent,
                COUNT(*) as call_count,
                ROUND(AVG(CAST(ghost_resolved AS REAL))::numeric * 100, 1) as ghost_rate_pct,
                ROUND(AVG(CAST(transcript_resolved AS REAL))::numeric * 100, 1) as claimed_resolution_pct,
                ROUND(AVG(CAST(behavioural_resolved AS REAL))::numeric * 100, 1) as true_resolution_pct,
                ROUND(AVG(attention_score)::numeric, 1) as avg_attention,
                SUM(CASE WHEN dominant_emotion IN ('frustrated','concerned','anxious') THEN 1 ELSE 0 END) as dissatisfied_count
            FROM calls
            WHERE processed=1
              AND intent IS NOT NULL
              AND intent != ''
              {filter_sql}
            GROUP BY intent
            ORDER BY call_count DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [_row(r) for r in rows]


@app.get("/dashboard/issues/{intent}/detail")
def issue_detail(intent: str):
    """
    Drill-down for one issue bucket (used by the "see suggestion" /
    dissatisfaction expansion in the perception dashboard):
      - a one-line suggested fix, grounded in the issue name + ghost rate
      - which specific customers were dissatisfied on this issue, and why
        (their call summary + dominant emotion), instead of a bare count.
    """
    with db() as conn:
        calls = conn.execute("""
            SELECT call_id, customer_name, agent_name, summary,
                   dominant_emotion, sentiment_label, attention_score, start_time_ms
            FROM calls
            WHERE intent = ? AND processed=1
              AND (sentiment_label IN ('negative','very_negative')
                   OR dominant_emotion IN ('frustrated','concerned','anxious'))
            ORDER BY attention_score DESC
        """, (intent,)).fetchall()
        stats = conn.execute("""
            SELECT COUNT(*) as call_count,
                   ROUND(AVG(CAST(ghost_resolved AS REAL))::numeric*100,1) as ghost_rate_pct
            FROM calls WHERE intent = ? AND processed=1
        """, (intent,)).fetchone()

    from .issue_suggestions import generate_issue_fix_suggestion
    suggestion = generate_issue_fix_suggestion(
        intent=intent,
        ghost_rate_pct=float(stats["ghost_rate_pct"] or 0) if stats else 0.0,
        call_count=int(stats["call_count"] or 0) if stats else 0,
    )
    return {
        "intent": intent,
        "suggestion": suggestion,
        "dissatisfied_calls": [_row(c) for c in calls],
    }


@app.get("/dashboard/satisfaction")
def satisfaction_metrics(from_date: str = None, to_date: str = None):
    """Dissatisfied customer count and breakdown for the given period."""
    filter_sql = _period_filter(from_date, to_date)
    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM calls WHERE processed=1 {filter_sql}"
        ).fetchone()[0]
        dissatisfied = conn.execute(f"""
            SELECT COUNT(*) FROM calls
            WHERE processed=1
              AND (sentiment_label IN ('negative','very_negative')
                   OR dominant_emotion IN ('frustrated','concerned','anxious'))
              {filter_sql}
        """).fetchone()[0]
        rows = conn.execute(f"""
            SELECT call_id, customer_name, agent_name, intent, summary,
                   sentiment_label, dominant_emotion, attention_score,
                   transcript_resolved, ghost_resolved, mood_shift_direction,
                   start_time_ms
            FROM calls
            WHERE processed=1
              AND (sentiment_label IN ('negative','very_negative')
                   OR dominant_emotion IN ('frustrated','concerned','anxious'))
              {filter_sql}
            ORDER BY attention_score DESC, start_time_ms DESC
            LIMIT 100
        """).fetchall()
        daily = conn.execute("""
            SELECT
                TO_CHAR(TO_TIMESTAMP(start_time_ms / 1000.0), 'YYYY-MM-DD') as day,
                COUNT(*) as total,
                SUM(CASE WHEN sentiment_label IN ('negative','very_negative')
                         OR dominant_emotion IN ('frustrated','concerned','anxious')
                    THEN 1 ELSE 0 END) as dissatisfied
            FROM calls WHERE processed=1 AND start_time_ms IS NOT NULL
            GROUP BY TO_CHAR(TO_TIMESTAMP(start_time_ms / 1000.0), 'YYYY-MM-DD')
            ORDER BY day DESC
            LIMIT 14
        """).fetchall()
    return {
        "total_calls": total,
        "dissatisfied_count": dissatisfied,
        "dissatisfied_rate_pct": round(dissatisfied / total * 100, 1) if total else 0,
        "calls": [_row(r) for r in rows],
        "daily_trend": [_row(r) for r in daily],
    }


@app.get("/dashboard/rude-agents")
def rude_agents(min_calls: int = 3):
    """Agents flagged for behavior patterns linked to customer dissatisfaction."""
    with db() as conn:
        rows = conn.execute("""
            SELECT
                agent_name,
                COUNT(*) as total_calls,
                SUM(CASE WHEN mood_shift=1
                         AND (mood_shift_direction LIKE '%%negative%%'
                              OR mood_shift_direction LIKE '%%worse%%'
                              OR mood_shift_direction = 'down'
                              OR mood_shift_direction LIKE '%%angr%%'
                              OR mood_shift_direction LIKE '%%frustrat%%')
                    THEN 1 ELSE 0 END) as worsened_mood_calls,
                SUM(CASE WHEN dominant_emotion IN ('frustrated','concerned','anxious')
                    THEN 1 ELSE 0 END) as negative_emotion_calls,
                ROUND(AVG(attention_score)::numeric, 1) as avg_attention,
                ROUND(AVG(sentiment_score)::numeric, 4) as avg_sentiment,
                SUM(CASE WHEN attention_score >= 70 THEN 1 ELSE 0 END) as high_attention_calls,
                SUM(ghost_resolved) as ghost_calls
            FROM calls WHERE processed=1
            GROUP BY agent_name
            HAVING COUNT(*) >= ?
            ORDER BY worsened_mood_calls DESC, negative_emotion_calls DESC
        """, (min_calls,)).fetchall()

    result = []
    for r in rows:
        d = _row(r)
        total = d["total_calls"] or 1
        worsened_rate  = (d["worsened_mood_calls"] or 0) / total
        neg_rate       = (d["negative_emotion_calls"] or 0) / total
        attention_norm = float(d["avg_attention"] or 0) / 100
        rudeness_score = round(worsened_rate * 50 + neg_rate * 30 + attention_norm * 20, 1)
        d["rudeness_score"]       = rudeness_score
        d["worsened_mood_pct"]    = round(worsened_rate * 100, 1)
        d["neg_emotion_pct"]      = round(neg_rate * 100, 1)
        d["ghost_rate_pct"]       = round((d["ghost_calls"] or 0) / total * 100, 1)
        d["flagged"]              = rudeness_score > 20 or worsened_rate > 0.35
        result.append(d)

    result.sort(key=lambda x: -x["rudeness_score"])
    flagged_agents = [r for r in result if r["flagged"]]
    return {
        "total_flagged": len(flagged_agents),
        "agents":         result,
    }


@app.get("/dashboard/spam-callers")
def spam_callers(limit: int = 50):
    """
    Callers whose pattern suggests low-value repeat contact — NOT the same
    thing as a customer who keeps calling back because a real issue was
    never fixed.

    Fix: self-service call volume previously counted toward the spam score
    regardless of whether those calls were ever actually resolved — so a
    customer calling 3x about a password reset that never got fixed still
    scored the full self-service weight (only NON-self-service unresolved
    calls were dampened before). Now self_service_calls only counts calls
    in a self-service topic that were ALSO behaviourally resolved, and both
    the self-service and volume components are dampened by the customer's
    overall unresolved-call share — so someone stuck in an unresolved loop
    no longer gets flagged as spam just for calling back repeatedly.
    """
    with db() as conn:
        # Topic buckets: map intent keywords → canonical topic
        TOPIC_CASES = [
            ("balance",      "balance check"),
            ("hour",         "branch hours"),
            ("branch",       "branch hours"),
            ("password",     "password reset"),
            ("checkbook",    "checkbook order"),
            ("appointment",  "appointment"),
            ("schedule",     "appointment"),
            ("bill",         "bill payment"),
            ("transfer",     "transfer"),
            ("credit card",  "card issue"),
            ("lost card",    "card issue"),
            ("replace",      "card issue"),
            ("statement",    "statement"),
            ("fee",          "fee enquiry"),
            ("interest",     "fee enquiry"),
            ("atm",          "atm"),
            ("pin",          "pin reset"),
        ]
        # Build a CASE expression that buckets each intent into a topic
        # Use %% to escape % for psycopg2 (which treats % as param placeholder)
        when_clauses = "\n".join(
            f"WHEN LOWER(intent) LIKE '%%{kw}%%' THEN '{topic}'"
            for kw, topic in TOPIC_CASES
        )
        # Self-service topics (could be handled digitally)
        SS_TOPICS = {'balance check','branch hours','password reset',
                     'checkbook order','statement','atm','pin reset','fee enquiry'}
        ss_topic_list = ", ".join(f"'{t}'" for t in SS_TOPICS)

        rows = conn.execute(f"""
            WITH topic_calls AS (
                SELECT
                    customer_name,
                    CASE {when_clauses}
                         ELSE 'other'
                    END as topic,
                    duration_s, attention_score, sentiment_score, start_time_ms,
                    behavioural_resolved
                FROM calls WHERE processed=1
            )
            SELECT
                customer_name,
                COUNT(*) as total_calls,
                ROUND(AVG(duration_s)::numeric, 1) as avg_duration_s,
                COUNT(DISTINCT topic) as distinct_topics,
                -- only count a self-service call toward the spam score if it
                -- was actually resolved — an unresolved self-service call is
                -- an escalation failure, not trivial/spam contact
                SUM(CASE WHEN topic IN ({ss_topic_list}) AND behavioural_resolved = 1
                    THEN 1 ELSE 0 END) as self_service_resolved_calls,
                SUM(CASE WHEN topic IN ({ss_topic_list})
                    THEN 1 ELSE 0 END) as self_service_total_calls,
                SUM(CASE WHEN behavioural_resolved = 0
                    THEN 1 ELSE 0 END) as unresolved_calls,
                ROUND(AVG(attention_score)::numeric, 1) as avg_attention,
                ROUND(AVG(sentiment_score)::numeric, 4) as avg_sentiment,
                MAX(start_time_ms) as last_call_ms
            FROM topic_calls
            GROUP BY customer_name
            HAVING COUNT(*) >= 3
            ORDER BY total_calls DESC
        """).fetchall()

    result = []
    for r in rows:
        d = _row(r)
        total             = d["total_calls"]
        distinct          = max(d["distinct_topics"] or 1, 1)
        ss_resolved       = d["self_service_resolved_calls"] or 0
        ss_total          = d["self_service_total_calls"] or 0
        ss_rate           = ss_resolved / total   # only resolved ones count toward spam
        unresolved        = d["unresolved_calls"] or 0
        unresolved_share  = unresolved / total
        # repeat_rate: how often they call about the same topic bucket
        repeat_rate       = 1 - (min(distinct, total) / total)
        # Dampen BOTH volume and repeat contribution by how much of this
        # customer's contact was genuinely unresolved — a customer calling
        # back repeatedly about something still broken should score low
        # across the board, not just on the repeat-rate component.
        volume_pts        = (min(total, 15) / 15) * 20 * (1 - unresolved_share)
        ss_pts            = ss_rate * 50
        repeat_pts        = repeat_rate * 30 * (1 - unresolved_share)
        spam_score        = round(ss_pts + repeat_pts + volume_pts, 1)
        d["spam_score"]                  = spam_score
        d["self_service_calls"]          = ss_total
        d["self_service_resolved_calls"] = ss_resolved
        d["self_service_pct"]            = round(ss_rate * 100, 1)
        d["repeat_rate_pct"]             = round(repeat_rate * 100, 1)
        d["unresolved_calls"]            = unresolved
        # Don't flag as spam if >50% of calls were unresolved —
        # that's a service failure loop, not trivial/spam behaviour.
        d["flagged"]                     = spam_score > 50 and unresolved_share < 0.5
        result.append(d)

    result.sort(key=lambda x: -x["spam_score"])
    all_flagged = [r for r in result if r["flagged"]]
    return {
        "total_flagged": len(all_flagged),
        "callers":        all_flagged[:limit],
    }


@app.get("/dashboard/performance")
def agent_performance():
    """Composite performance score per agent (0 EUR"100 scale)."""
    with db() as conn:
        rows = conn.execute("""
            SELECT
                agent_name,
                COUNT(*) as total_calls,
                SUM(CASE WHEN behavioural_resolved=1 THEN 1 ELSE 0 END) as true_resolved,
                SUM(CASE WHEN transcript_resolved=1 THEN 1 ELSE 0 END) as claimed_resolved,
                SUM(ghost_resolved) as ghost_calls,
                ROUND(AVG(CAST(ghost_resolved AS REAL))::numeric, 4) as ghost_rate,
                ROUND(AVG(CAST(behavioural_resolved AS REAL))::numeric, 4) as true_resolution_rate,
                ROUND(AVG(attention_score)::numeric, 1) as avg_attention,
                ROUND(AVG(sentiment_score)::numeric, 4) as avg_sentiment,
                ROUND(AVG(duration_s)::numeric, 1) as avg_duration_s,
                SUM(CASE WHEN dominant_emotion NOT IN ('frustrated','concerned','angry','anxious')
                    THEN 1 ELSE 0 END) as positive_outcomes,
                SUM(CASE WHEN mood_shift=1
                         AND (mood_shift_direction LIKE '%%positive%%'
                              OR mood_shift_direction LIKE '%%better%%'
                              OR mood_shift_direction LIKE '%%calm%%')
                    THEN 1 ELSE 0 END) as positive_mood_shifts
            FROM calls WHERE processed=1
            GROUP BY agent_name
            HAVING COUNT(*) >= 1
            ORDER BY true_resolved DESC
        """).fetchall()

    result = []
    for r in rows:
        d = _row(r)
        total = d["total_calls"] or 1
        ghost_rate       = float(d["ghost_rate"] or 0)
        true_res_rate    = float(d["true_resolution_rate"] or 0)
        avg_sentiment    = float(d["avg_sentiment"]) if d["avg_sentiment"] is not None else 0.5
        avg_attention    = float(d["avg_attention"] or 50)
        # Composite score components (sum to 100)
        resolution_pts = true_res_rate * 40
        ghost_pts      = (1 - ghost_rate) * 25
        sentiment_norm = max(0, (avg_sentiment + 1) / 2)
        sentiment_pts  = sentiment_norm * 20
        attention_pts  = max(0, (100 - avg_attention) / 100) * 15
        score = round(resolution_pts + ghost_pts + sentiment_pts + attention_pts, 1)
        d["performance_score"]      = max(0, min(100, score))
        d["positive_outcome_pct"]   = round((d["positive_outcomes"] or 0) / total * 100, 1)
        d["ghost_rate_pct"]         = round(ghost_rate * 100, 1)
        d["true_resolution_pct"]    = round(true_res_rate * 100, 1)
        d["claimed_resolution_pct"] = round((d["claimed_resolved"] or 0) / total * 100, 1)
        result.append(d)

    result.sort(key=lambda x: -x["performance_score"])
    for i, r in enumerate(result):
        r["rank"] = i + 1
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=API_HOST, port=API_PORT, reload=True)