"""
backend/pipeline/ghost.py
--------------------------
Ghost Resolution Engine — the core differentiator.

After all calls are transcribed and analysed, this module:
1. Detects ghost resolutions: transcript says resolved BUT customer
   called back within GHOST_WINDOW_MIN minutes.
2. Computes behavioural_resolved: resolved AND no callback.
3. Computes sequence_resolved: for ghosts, whether the callback call
   itself closed the loop (resolved, and wasn't itself a ghost that
   needed a third call). This is what separates a real failure from
   a quick self-correcting follow-up, and is used to weight the
   attention-queue boost instead of applying the same +30 to every
   ghost regardless of how the story actually ended.
4. Computes per-agent ghost rates.
5. Computes customer frustration trajectory (mood arc across all calls).

This is pure SQL + Python — no LLM needed. The behavioural signal
is more reliable than any LLM judgment about resolution.

Key insight from the data:
  507 / 1441 calls (35.2%) are ghost resolutions.
  David: 40.1% ghost rate (worst)
  Linda: 30.1% ghost rate (best)
  That 10-point gap is actionable and invisible to any per-call tool.
"""
from __future__ import annotations
from datetime import datetime
from typing import Dict, List
from ..config import GHOST_WINDOW_MIN
from ..db import db


def _same_intent(a: str | None, b: str | None) -> bool:
    """
    Two intents are considered the same when they are identical non-null strings.
    NULL / empty intent on either side → treat as unknown → not a ghost
    (better to miss a ghost than to falsely flag a different-issue callback).
    """
    return bool(a and b and a.strip().lower() == b.strip().lower())


def compute_ghost_resolutions() -> int:
    """
    For every call, check if the same customer made another call
    within GHOST_WINDOW_MIN minutes afterward ON THE SAME INTENT.

    A callback on a different topic is a new issue, not a failed resolution —
    only same-intent callbacks within the window count as ghost resolutions.

    Updates ghost_resolved, ghost_callback_id, ghost_gap_min,
    behavioural_resolved, and sequence_resolved on the calls table.
    Returns count of ghost resolutions found.
    """
    ghost_count = 0
    with db() as conn:
        calls = conn.execute("""
            SELECT call_id, customer_name, start_time_ms, end_time_ms,
                   transcript_resolved, intent
            FROM calls ORDER BY customer_name, start_time_ms
        """).fetchall()

        # Group by customer
        by_customer: Dict[str, list] = {}
        for c in calls:
            by_customer.setdefault(c["customer_name"], []).append(dict(c))

        for customer, clist in by_customer.items():
            sorted_calls = sorted(clist, key=lambda x: x["start_time_ms"])

            # Pass 1 — detect ghosts exactly as before, keyed by call_id.
            # Nothing about ghost DETECTION changes here, only that we now
            # keep the per-call results around so pass 2 can look up how
            # any given callback call itself turned out.
            ghost_info: Dict[str, dict] = {}
            for i, call in enumerate(sorted_calls):
                is_ghost = False
                callback_id = None
                gap_min = None

                # Look ahead for a same-intent callback within the ghost window
                for next_call in sorted_calls[i + 1:]:
                    gap = (next_call["start_time_ms"] - call["end_time_ms"]) / 1000 / 60
                    if gap > GHOST_WINDOW_MIN:
                        break
                    if gap >= 0 and _same_intent(call.get("intent"), next_call.get("intent")):
                        is_ghost = True
                        callback_id = next_call["call_id"]
                        gap_min = round(gap, 1)
                        ghost_count += 1
                        break

                ghost_info[call["call_id"]] = {
                    "is_ghost":    is_ghost,
                    "callback_id": callback_id,
                    "gap_min":     gap_min,
                }

            by_id = {c["call_id"]: c for c in sorted_calls}

            # Pass 2 — for each ghost, check whether the callback call itself
            # closed the loop. sequence_resolved is only meaningful for calls
            # that were flagged as a ghost; it stays NULL otherwise.
            for call in sorted_calls:
                info        = ghost_info[call["call_id"]]
                is_ghost    = info["is_ghost"]
                callback_id = info["callback_id"]
                gap_min     = info["gap_min"]

                sequence_resolved = None
                if is_ghost and callback_id in by_id:
                    cb_call = by_id[callback_id]
                    cb_info = ghost_info[callback_id]
                    sequence_resolved = (
                        1 if (cb_call["transcript_resolved"] and not cb_info["is_ghost"]) else 0
                    )

                # Behavioural resolution:
                # resolved AND customer did NOT call back within window
                behavioural = (
                    1 if (call["transcript_resolved"] and not is_ghost) else 0
                )

                conn.execute("""
                    UPDATE calls SET
                        ghost_resolved        = ?,
                        ghost_callback_id     = ?,
                        ghost_gap_min         = ?,
                        behavioural_resolved  = ?,
                        sequence_resolved     = ?
                    WHERE call_id = ?
                """, (
                    1 if is_ghost else 0,
                    callback_id,
                    gap_min,
                    behavioural,
                    sequence_resolved,
                    call["call_id"],
                ))

    return ghost_count


def compute_customer_trajectories() -> List[Dict]:
    """
    Returns the customer frustration trajectory — mood arc across
    all calls per customer, ordered by call time.
    Used by the Customer Trajectory dashboard view.
    """
    mood_score = {
        "satisfied": 5, "calm": 4, "confused": 3,
        "frustrated": 2, "angry": 1,
    }
    with db() as conn:
        rows = conn.execute("""
            SELECT customer_name, call_id, start_time_ms,
                   mood_start, ghost_resolved, transcript_resolved,
                   behavioural_resolved, intent, attention_score, agent_name
            FROM calls ORDER BY customer_name, start_time_ms
        """).fetchall()

    by_customer: Dict[str, list] = {}
    for r in rows:
        by_customer.setdefault(r["customer_name"], []).append(dict(r))

    trajectories = []
    for customer, calls in by_customer.items():
        moods = [mood_score.get(c["mood_start"], 3) for c in calls]
        trend = "stable"
        if len(moods) >= 2:
            if moods[-1] < moods[0] - 0.5:
                trend = "deteriorating"
            elif moods[-1] > moods[0] + 0.5:
                trend = "improving"

        ghost_rate = sum(1 for c in calls if c["ghost_resolved"]) / len(calls)
        trajectories.append({
            "customer_name":    customer,
            "total_calls":      len(calls),
            "ghost_rate":       round(ghost_rate, 3),
            "mood_trend":       trend,
            "avg_attention":    round(sum(c["attention_score"] for c in calls) / len(calls), 1),
            "recurrent_issues": _find_recurrent_issues(calls),
            "calls":            calls,
        })

    return sorted(trajectories, key=lambda x: x["ghost_rate"], reverse=True)


def _find_recurrent_issues(calls: list) -> List[str]:
    """
    Finds intents that appear in multiple calls for the same customer.
    A recurrent issue = customer called about the same thing more than once.
    """
    intent_counts: Dict[str, int] = {}
    for c in calls:
        intent = (c.get("intent") or "").lower().strip()
        if intent:
            # Simple keyword grouping — good enough for demo
            for keyword in ["card", "transfer", "payment", "account",
                            "loan", "balance", "statement", "fraud"]:
                if keyword in intent:
                    intent_counts[keyword] = intent_counts.get(keyword, 0) + 1
                    break

    return [k for k, v in intent_counts.items() if v > 1]


def get_agent_ghost_rates() -> List[Dict]:
    """Per-agent ghost resolution rates — the unique agent leaderboard."""
    with db() as conn:
        rows = conn.execute("""
            SELECT
                agent_name,
                COUNT(*) as total,
                SUM(ghost_resolved) as ghost_count,
                AVG(CAST(ghost_resolved AS REAL)) as ghost_rate,
                AVG(duration_s) as avg_duration_s,
                AVG(CAST(behavioural_resolved AS REAL)) as true_resolution_rate,
                AVG(CAST(transcript_resolved AS REAL)) as claimed_resolution_rate,
                AVG(attention_score) as avg_attention_score
            FROM calls
            GROUP BY agent_name
            ORDER BY ghost_rate DESC
        """).fetchall()

    return [dict(r) for r in rows]