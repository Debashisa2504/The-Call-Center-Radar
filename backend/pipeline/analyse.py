"""
backend/pipeline/analyse.py
=============================
Step 2 — Citation-first call analysis with 7-emotion sentiment.

Improvement from CortexV: 7-emotion vector sentiment model
-----------------------------------------------------------
CortexV's sentiment analyzer returns a rich structured model per speaker:
  - sentiment_score : float 0.0 (very negative) to 1.0 (very positive)
  - dominant_emotion: one of 7 fixed emotion labels
  - emotion_scores  : {emotion: float} summing to 1.0

The original Call Radar used a single 5-value mood string.  We now return
the full 7-emotion model in one combined LLM call that also handles
intent/resolution/attention — no extra API cost.

Emotion set (same 7 as CortexV):
  engaged, enthusiastic, frustrated, anxious, concerned, neutral, happy

The emotion vectors are stored as JSON in the calls table and used by the
frontend MoodTimeline component to show nuanced mood arcs:
  "anxious but engaged" vs "frustrated and disengaged" — invisible with a
  single mood label.

Brief compliance
----------------
Every judgment MUST include a timestamp_s and verbatim quote.
No evidence = 0 score.  Wrong evidence = negative score.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..config import ANALYSIS_MODEL, make_openai_client

client = make_openai_client()

# The 7 emotion labels (matches CortexV exactly)
EMOTIONS = ["engaged", "enthusiastic", "frustrated", "anxious",
            "concerned", "neutral", "happy"]

SYSTEM_PROMPT = """You are a precision financial services call analyst.
You receive a timestamped transcript of a bank support call and return
a single strict JSON object — no prose, no markdown, no code fences.

CRITICAL RULES:
1. Every judgment must be supported by a direct verbatim quote from the transcript.
2. timestamp_s must be the start_s of the turn containing that quote.
3. All quotes must be verbatim substrings of the transcript text.
4. summary must be 40 words or fewer.
5. attention_score 0-100: 100 = manager must listen now.
6. emotion_scores values must sum to exactly 1.0.
7. sentiment_score: 0.0 = very negative, 1.0 = very positive, 0.5 = neutral.

Return exactly this JSON structure:
{
  "intent": "one sentence — what the customer wanted",
  "intent_evidence": {
    "timestamp_s": <number>,
    "quote": "<verbatim from transcript>"
  },

  "mood_start": "calm|frustrated|angry|confused|satisfied",

  "mood_shift": true|false,
  "mood_shift_timestamp_s": <number or null>,
  "mood_shift_quote": "<verbatim from transcript or null>",
  "mood_shift_direction": "improved|worsened|null",

  "transcript_resolved": true|false,
  "resolved_evidence": {
    "timestamp_s": <number>,
    "quote": "<verbatim from transcript>"
  },

  "summary": "<40 words or fewer — what happened on this call>",

  "attention_score": <0-100>,
  "attention_reason": "<one sentence why this score>",

  "key_moments": [
    {
      "timestamp_s": <number>,
      "quote": "<verbatim>",
      "label": "<what happened here>"
    }
  ],

  "sentiment": {
    "overall": {
      "score": <0.0-1.0>,
      "label": "positive|negative|neutral|mixed",
      "summary": "<2-3 sentences describing overall call tone and dynamics>"
    },
    "agent": {
      "score": <0.0-1.0>,
      "dominant_emotion": "<one of: engaged|enthusiastic|frustrated|anxious|concerned|neutral|happy>",
      "emotion_scores": {
        "engaged": <0.0-1.0>,
        "enthusiastic": <0.0-1.0>,
        "frustrated": <0.0-1.0>,
        "anxious": <0.0-1.0>,
        "concerned": <0.0-1.0>,
        "neutral": <0.0-1.0>,
        "happy": <0.0-1.0>
      }
    },
    "customer": {
      "score": <0.0-1.0>,
      "dominant_emotion": "<one of: engaged|enthusiastic|frustrated|anxious|concerned|neutral|happy>",
      "emotion_scores": {
        "engaged": <0.0-1.0>,
        "enthusiastic": <0.0-1.0>,
        "frustrated": <0.0-1.0>,
        "anxious": <0.0-1.0>,
        "concerned": <0.0-1.0>,
        "neutral": <0.0-1.0>,
        "happy": <0.0-1.0>
      }
    }
  }
}"""

_EMPTY_EMOTION_SCORES = {e: 0.0 for e in EMOTIONS}
_EMPTY_EMOTION_SCORES["neutral"] = 1.0


def _default_sentiment() -> Dict:
    return {
        "overall": {"score": 0.5, "label": "neutral", "summary": ""},
        "agent":    {"score": 0.5, "dominant_emotion": "neutral",
                     "emotion_scores": dict(_EMPTY_EMOTION_SCORES)},
        "customer": {"score": 0.5, "dominant_emotion": "neutral",
                     "emotion_scores": dict(_EMPTY_EMOTION_SCORES)},
    }


def _normalise_emotion_scores(scores: Any) -> Dict[str, float]:
    """Ensure emotion_scores is a valid dict summing to 1.0."""
    if not isinstance(scores, dict):
        return dict(_EMPTY_EMOTION_SCORES)
    out = {}
    for e in EMOTIONS:
        try:
            out[e] = float(scores.get(e, 0.0))
        except (TypeError, ValueError):
            out[e] = 0.0
    total = sum(out.values())
    if total > 0:
        out = {k: round(v / total, 4) for k, v in out.items()}
    else:
        out = dict(_EMPTY_EMOTION_SCORES)
    return out


def _parse_sentiment(raw: Any) -> Dict:
    """Extract and validate the sentiment block from the LLM response."""
    if not isinstance(raw, dict):
        return _default_sentiment()

    def parse_speaker(block: Any) -> Dict:
        if not isinstance(block, dict):
            return {"score": 0.5, "dominant_emotion": "neutral",
                    "emotion_scores": dict(_EMPTY_EMOTION_SCORES)}
        try:
            score = float(block.get("score", 0.5))
        except (TypeError, ValueError):
            score = 0.5
        dominant = block.get("dominant_emotion", "neutral")
        if dominant not in EMOTIONS:
            dominant = "neutral"
        return {
            "score":           round(max(0.0, min(1.0, score)), 4),
            "dominant_emotion": dominant,
            "emotion_scores":   _normalise_emotion_scores(
                                    block.get("emotion_scores")),
        }

    overall_raw = raw.get("overall", {})
    try:
        overall_score = float(overall_raw.get("score", 0.5))
    except (TypeError, ValueError):
        overall_score = 0.5

    return {
        "overall": {
            "score":   round(max(0.0, min(1.0, overall_score)), 4),
            "label":   overall_raw.get("label", "neutral"),
            "summary": overall_raw.get("summary", ""),
        },
        "agent":    parse_speaker(raw.get("agent")),
        "customer": parse_speaker(raw.get("customer")),
    }


def _format_transcript(turns: List[Dict]) -> str:
    lines = []
    for t in turns:
        role = "AGENT" if t["speaker"] == "agent" else "CUSTOMER"
        lines.append(f"[{t['start_s']:.1f}s] {role}: {t['text']}")
    return "\n".join(lines)


def _parse_response(raw: str) -> Dict[str, Any]:
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    return json.loads(raw)


def analyse_call(turns: List[Dict], call_id: str) -> Dict[str, Any]:
    """
    Analyses a transcript and returns the full analysis dict.

    Returns:
        dict with all brief-required fields plus the 7-emotion sentiment block.
        The sentiment block is stored as JSON in the database and returned in
        the API response for the frontend mood timeline.
    """
    if not turns:
        return {
            "intent": "No audio content",
            "intent_evidence": {"timestamp_s": 0, "quote": ""},
            "mood_start": "calm",
            "mood_shift": False,
            "mood_shift_timestamp_s": None,
            "mood_shift_quote": None,
            "mood_shift_direction": None,
            "transcript_resolved": False,
            "resolved_evidence": {"timestamp_s": 0, "quote": ""},
            "summary": "Call contained no transcribable audio.",
            "attention_score": 0,
            "attention_reason": "Empty transcript.",
            "key_moments": [],
            "sentiment": _default_sentiment(),
        }

    transcript_text = _format_transcript(turns)
    user_prompt     = f"Call ID: {call_id}\n\nTranscript:\n{transcript_text}"

    response = client.chat.completions.create(
        model=ANALYSIS_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    result = _parse_response(response.choices[0].message.content)

    # Validate and normalise the sentiment block
    result["sentiment"] = _parse_sentiment(result.get("sentiment"))
    return result
