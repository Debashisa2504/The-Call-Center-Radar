"""
backend/pipeline/suggestions.py
=================================
Contextual follow-up question generator.

Adapted from CortexV (app/services/chat/suggestions.py).

After each call is analysed, generate 3 follow-up questions a manager
is likely to ask about this specific call — referencing actual names,
amounts, and issues from the call, not generic prompts.

CortexV's key insight: banning generic questions like "Tell me more"
in the system prompt forces the model to generate specific, actionable
questions that reference what was actually discussed.

These are stored alongside the call and surfaced in the call detail view
to help managers quickly drill into the most relevant follow-up actions.
"""
from __future__ import annotations

import json
from typing import List

from ..config import ANALYSIS_MODEL, make_openai_client

client = make_openai_client()

_SYSTEM = (
    "You are a bank call-centre management assistant. Given a call summary and analysis, "
    "suggest exactly 3 concise follow-up questions a branch manager is likely to ask next.\n\n"
    "Rules:\n"
    "- Questions must reference specific details from THIS call (names, amounts, issue type).\n"
    "- Keep each question under 12 words.\n"
    "- Never suggest generic questions like 'Tell me more' or 'What else happened'.\n"
    "- Examples of good suggestions:\n"
    "    'Why did the customer call back within 4 minutes?'\n"
    "    'Did Robert follow the fraud disclosure process here?'\n"
    "    'Was the fee waiver approved by a supervisor?'\n"
    "Return ONLY a valid JSON array of 3 strings. No explanation, no markdown."
)


def generate_call_suggestions(
    intent:         str,
    summary:        str,
    agent_name:     str,
    customer_name:  str,
    ghost_resolved: bool,
    ghost_gap_min:  float = None,
    attention_reason: str = "",
) -> List[str]:
    """
    Generate 3 specific follow-up questions for a call detail view.
    Falls back to a sensible default list on any failure.
    """
    context = (
        f"Customer: {customer_name}. Agent: {agent_name}.\n"
        f"Intent: {intent}\n"
        f"Summary: {summary}\n"
        f"Attention reason: {attention_reason}\n"
    )
    if ghost_resolved and ghost_gap_min is not None:
        context += (
            f"Ghost resolution: customer called back {ghost_gap_min:.0f} minutes "
            f"after this call was marked resolved.\n"
        )

    try:
        resp = client.chat.completions.create(
            model=ANALYSIS_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": context},
            ],
            temperature=0.7,
            max_tokens=160,
        )
        raw         = (resp.choices[0].message.content or "").strip()
        suggestions = json.loads(raw)
        if isinstance(suggestions, list):
            return [str(s) for s in suggestions[:3]]
    except Exception as exc:
        print(f"[suggestions] failed: {exc}")

    # Sensible fallback defaults
    defaults = [
        f"Was {customer_name}'s issue fully resolved this call?",
        f"Did {agent_name} follow all required disclosures?",
        "Should this be escalated to a supervisor?",
    ]
    return defaults
