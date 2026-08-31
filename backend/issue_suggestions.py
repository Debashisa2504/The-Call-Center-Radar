"""
backend/pipeline/issue_suggestions.py
--------------------------------------
One-line, actionable "how to reduce repeat contact on this issue" text for
the Customer Perception → Issue Frequency drill-down (see:
GET /dashboard/issues/{intent}/detail in main.py).

Kept separate from pipeline/suggestions.py (which generates per-call
follow-up questions) since this is a different, simpler generation task
keyed on the issue bucket rather than a single call's transcript.

Rule-based on keywords in the intent text. If your existing suggestions.py
already has an LLM client set up (e.g. via config.make_openai_client),
swap RULES-based matching below for a real model call using the same
pattern as generate_call_suggestions — the function signature here is
deliberately the same shape either way.
"""
from __future__ import annotations

# (keywords, suggestion) — first matching rule wins
_RULES = [
    (("hour", "branch"),
     "Publish branch hours prominently near the support/contact page so customers don't need to call to check."),
    (("balance",),
     "Surface account balance in a one-tap widget in the mobile app or via SMS balance check to deflect these calls."),
    (("password", "pin", "reset"),
     "Add a self-service reset flow with SMS/email verification so customers don't need an agent for a routine reset."),
    (("checkbook", "check book"),
     "Let customers request a checkbook reorder online or in-app instead of calling."),
    (("appointment", "schedule"),
     "Add online appointment booking with real-time branch availability."),
    (("bill", "payment"),
     "Send proactive payment reminders and confirmations to cut down on status-check calls."),
    (("card", "lost", "replace"),
     "Enable instant card lock/replacement requests in-app to reduce urgent call volume."),
    (("statement",),
     "Make recent statements downloadable from the app / online banking without a call."),
    (("fee", "interest"),
     "Add a fee breakdown screen in the app so customers can self-diagnose charges before calling."),
    (("atm",),
     "Publish a live ATM locator/status map to cut down on location and outage calls."),
    (("transfer",),
     "Simplify the in-app transfer flow and add clearer confirmation messaging to reduce follow-up calls."),
]


def generate_issue_fix_suggestion(intent: str, ghost_rate_pct: float, call_count: int) -> str:
    """
    Return a one-sentence suggested fix for an issue bucket, grounded in the
    issue's name and its ghost rate (calls marked resolved where the
    customer called back anyway).
    """
    text = (intent or "").lower()

    for keywords, suggestion in _RULES:
        if any(k in text for k in keywords):
            note = ""
            if ghost_rate_pct and ghost_rate_pct > 20:
                note = (
                    f" ({ghost_rate_pct}% of these calls were marked resolved but the "
                    "customer called back — prioritize this one.)"
                )
            return suggestion + note

    base = (
        f"No specific playbook match for '{intent}' yet — review the {call_count} "
        "transcripts to identify a common root cause."
    )
    if ghost_rate_pct and ghost_rate_pct > 20:
        base += (
            f" A {ghost_rate_pct}% ghost rate suggests the current resolution "
            "process isn't actually closing the loop."
        )
    return base