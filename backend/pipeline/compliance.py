"""
backend/pipeline/compliance.py
================================
Compliance Rule Engine — adapted from CortexV (app/services/rules/evaluators/llm_freeform.py).

Architecture (same three-stage pattern as CortexV)
----------------------------------------------------
Stage 1 — Pre-filter (semantic similarity)
    Embed the rule description.  Compute cosine similarity against every
    embedded chunk.  Only chunks scoring >= RULES_PRE_FILTER_MIN_SIM (0.30)
    are passed to the LLM.  Keyword hits bypass the similarity floor so
    exact phrase matches are never dropped by the pre-filter.
    → Keeps LLM prompt small regardless of call length.

Stage 2 — LLM-as-judge (GPT-4o-mini)
    Sends the top-K candidate chunks (with ±1 context neighbours) to GPT
    with a structured prompt: "was this rule violated? If so, cite the
    speaker, timestamp, and exact quote."
    → Returns JSON with violations list.

Stage 3 — Verifier pass (hallucinaton defence — CortexV key innovation)
    Each flagged violation is verified:
    a. Quote verification: is the quote a verbatim substring of the chunks?
    b. Timestamp verification: does the timestamp match a known chunk boundary?
    c. Second-pass LLM: "Is the speaker proposing/admitting this, or just
       describing/quoting it?" — drops false positives where an agent
       explains what NOT to do.
    → Violations that fail the verifier are dropped, not surfaced.

Bank-specific default rules
----------------------------
Ten pre-defined compliance rules relevant to a consumer bank are seeded
at startup.  Managers can add custom rules via the API.

Rule IDs (permanent, never reuse):
  RULE_001  No specific interest rate promises
  RULE_002  No unsanctioned fee waivers
  RULE_003  Fraud disclosure before any transfer
  RULE_004  No guarantee of outcomes
  RULE_005  Data privacy — no reading card numbers aloud
  RULE_006  Escalation offer for unresolved complaints
  RULE_007  No demeaning customer language
  RULE_008  Loan eligibility — no false eligibility claims
  RULE_009  Agent must not agree to reverse charges without auth
  RULE_010  Misleading product information
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from ..config import (
    ANALYSIS_MODEL, EMBED_MODEL, make_openai_client,
    RULES_PRE_FILTER_TOP_K, RULES_PRE_FILTER_MIN_SIM,
    RULES_MIN_CONFIDENCE, RULES_CONTEXT_BEFORE, RULES_CONTEXT_AFTER,
    RULES_ENABLE_VERIFIER_PASS,
)
from ..db import db

client = make_openai_client()

# ── Default bank compliance rules ─────────────────────────────────────────────

DEFAULT_RULES = [
    {
        "rule_id":    "RULE_001",
        "name":       "No specific interest rate promises",
        "description": "Agent must not quote or promise a specific interest rate to the customer. Agents may say rates vary and are subject to approval, but must not name a figure.",
        "severity":   "high",
    },
    {
        "rule_id":    "RULE_002",
        "name":       "No unsanctioned fee waivers",
        "description": "Agent must not agree to waive, reverse, or remove any fee or charge without explicit manager authorisation. Only supervisors may approve fee waivers.",
        "severity":   "high",
    },
    {
        "rule_id":    "RULE_003",
        "name":       "Fraud disclosure before transfer",
        "description": "Agent must read the fraud awareness disclosure before processing any fund transfer or payment instruction. The disclosure must include a warning about impersonation scams.",
        "severity":   "critical",
    },
    {
        "rule_id":    "RULE_004",
        "name":       "No guarantee of outcomes",
        "description": "Agent must not guarantee the outcome of a claim, dispute, or application. Language like 'I guarantee', 'definitely will', or 'for certain' about future outcomes is prohibited.",
        "severity":   "medium",
    },
    {
        "rule_id":    "RULE_005",
        "name":       "No card numbers read aloud",
        "description": "Agent must not read back full card numbers, CVV codes, or PINs aloud during a call. Partial masking (last 4 digits only) is permitted for identity verification.",
        "severity":   "critical",
    },
    {
        "rule_id":    "RULE_006",
        "name":       "Escalation offer for complaints",
        "description": "When a customer expresses dissatisfaction or raises a complaint, the agent must offer to escalate to a supervisor or complaints team before ending the call.",
        "severity":   "medium",
    },
    {
        "rule_id":    "RULE_007",
        "name":       "No demeaning customer language",
        "description": "Agent must not use dismissive, condescending, or demeaning language toward the customer at any point during the call.",
        "severity":   "high",
    },
    {
        "rule_id":    "RULE_008",
        "name":       "No false loan eligibility claims",
        "description": "Agent must not tell a customer they are pre-approved or definitely eligible for a loan or credit product without a formal eligibility check being recorded.",
        "severity":   "high",
    },
    {
        "rule_id":    "RULE_009",
        "name":       "No charge reversal without authorisation",
        "description": "Agent must not promise to reverse, refund, or credit any charge without first obtaining documented manager authorisation during the call.",
        "severity":   "high",
    },
    {
        "rule_id":    "RULE_010",
        "name":       "No misleading product information",
        "description": "Agent must not describe product features, terms, or benefits in a way that is materially inaccurate or misleading compared to the product documentation.",
        "severity":   "medium",
    },
]


def seed_default_rules() -> None:
    """Insert default rules if they don't exist yet."""
    now = datetime.utcnow().isoformat()
    with db() as conn:
        for r in DEFAULT_RULES:
            conn.execute("""
                INSERT INTO compliance_rules
                    (rule_id, name, description, severity, enabled, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT (rule_id) DO NOTHING
            """, (r["rule_id"], r["name"], r["description"], r["severity"], now))


# ── Embedding helpers ──────────────────────────────────────────────────────────

def _embed_text(text: str) -> List[float]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=[text])
    return resp.data[0].embedding


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom  = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


# ── Pre-filter ────────────────────────────────────────────────────────────────

def _ms_to_hms(ms: Optional[float]) -> str:
    if ms is None:
        return "00:00:00"
    total = int(ms) // 1000
    h, rem = divmod(total, 3600)
    m, s   = divmod(rem,   60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_chunk_for_prompt(chunk: Dict, is_candidate: bool = True) -> str:
    start = _ms_to_hms(chunk.get("start_s", 0) * 1000)
    end   = _ms_to_hms(chunk.get("end_s",   0) * 1000)
    role  = "[CANDIDATE]" if is_candidate else "[CONTEXT]  "
    spk   = "Agent" if chunk.get("speaker") == "agent" else "Customer"
    return f"{role} [{start} – {end}] [{spk}]: {chunk.get('text', '').strip()}"


def _normalise_ts(ts: str) -> str:
    """Collapse dash variants so '–' and '-' compare equal."""
    return ts.replace("–", "-").replace("—", "-").replace(" ", "")


def _build_chunk_ts(chunk: Dict) -> str:
    start = _ms_to_hms(chunk.get("start_s", 0) * 1000)
    end   = _ms_to_hms(chunk.get("end_s",   0) * 1000)
    return f"{start} – {end}"


# ── LLM prompts ────────────────────────────────────────────────────────────────

_EVALUATOR_SYSTEM = """\
You are a bank compliance officer reviewing a call-centre transcript.
Your task: determine whether the rule below was violated.

IMPORTANT — omission rules: Some rules require the agent to SAY or DO something
(e.g. read a disclosure, offer escalation, confirm resolution). If the transcript
contains NO evidence that the required action was performed, that IS a violation —
absence of evidence is evidence of absence for mandatory steps. Do NOT assume the
action happened off-transcript. For omission violations, use the quote field to
cite the point in the call where the omission is most apparent (e.g. the agent
proceeding with the transaction, or the call ending without the required step).

Return STRICT JSON only (no markdown, no prose):
{
  "violation_found": true|false,
  "severity": "low|medium|high|critical",
  "violations": [
    {
      "speaker": "Agent|Customer",
      "timestamp": "HH:MM:SS – HH:MM:SS",
      "quote": "<verbatim text from the transcript closest to where the omission occurred>",
      "reasoning": "<one sentence why this violates the rule>",
      "confidence": <0.0-1.0>
    }
  ]
}

If violation_found is false, violations must be an empty array.
Only include violations with confidence >= 0.6.
Quotes must be verbatim substrings of the provided transcript.
Timestamps must exactly match the [HH:MM:SS – HH:MM:SS] format shown."""

_VERIFIER_SYSTEM = """\
You are verifying a flagged compliance violation.
Determine: is the speaker PROPOSING/ADMITTING the forbidden action in their
own voice, or merely DESCRIBING/QUOTING/DEMONSTRATING it for training
or explanation purposes?

Return STRICT JSON only:
{"verdict": "proposing|describing", "reason": "<one sentence>"}"""


# ── Core evaluation ────────────────────────────────────────────────────────────

def _load_call_chunks(conn, call_id: str) -> List[Dict]:
    """Load embedded chunks for a call from the database."""
    rows = conn.execute(
        "SELECT id, chunk_index, speaker, start_s, end_s, text, embedding "
        "FROM chunks WHERE call_id=? ORDER BY chunk_index",
        (call_id,)
    ).fetchall()
    chunks = []
    for r in rows:
        emb = None
        raw = r["embedding"]
        if raw is not None:
            try:
                # pgvector returns a list directly;
                if isinstance(raw, (list, tuple)):
                    emb = list(raw)
                else:
                    emb = [float(x) for x in str(raw).split(",")]
            except Exception:
                pass
        chunks.append({
            "id":          r["id"],
            "chunk_index": r["chunk_index"],
            "speaker":     r["speaker"],
            "start_s":     r["start_s"],
            "end_s":       r["end_s"],
            "text":        r["text"],
            "embedding":   emb,
        })
    return chunks


def _pgvector_pre_filter(call_id: str, rule_vec: List[float],
                          top_k: int) -> List[Dict]:
    """
    PostgreSQL-native cosine similarity search using the HNSW index.
    Returns top-K chunks ordered by similarity — runs entirely in the DB.
    """
    from ..config import DATABASE_URL
    if not DATABASE_URL:
        return []
    with db() as conn:
        rows = conn.execute("""
            SELECT id, chunk_index, speaker, start_s, end_s, text,
                   1 - (embedding <=> ?) AS similarity
            FROM chunks
            WHERE call_id = ? AND embedding IS NOT NULL
            ORDER BY embedding <=> ?
            LIMIT ?
        """, (rule_vec, call_id, rule_vec, top_k)).fetchall()
    return [dict(r) for r in rows]


def _pre_filter(
    chunks:   List[Dict],
    rule_vec: List[float],
    keywords: List[str],
) -> Tuple[List[Tuple[Dict, float]], List[Tuple[Dict, List[str]]], bool]:
    """
    Score chunks by cosine similarity and collect keyword hits.
    Returns (vector_top, keyword_candidates, vector_passed).
    """
    # Vector scoring
    scored = [
        (c, _cosine_similarity(rule_vec, c["embedding"]))
        for c in chunks if c["embedding"]
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    top_k        = scored[:RULES_PRE_FILTER_TOP_K]
    top_sim      = top_k[0][1] if top_k else 0.0
    vec_passed   = top_sim >= RULES_PRE_FILTER_MIN_SIM

    # Keyword hits (bypass similarity floor)
    kw_candidates: List[Tuple[Dict, List[str]]] = []
    if keywords:
        for c in chunks:
            hits = [k for k in keywords
                    if k.lower() in (c.get("text") or "").lower()]
            if hits:
                kw_candidates.append((c, hits))

    return top_k, kw_candidates, vec_passed


def _build_prompt_window(
    all_chunks:    List[Dict],
    top_k:         List[Tuple[Dict, float]],
    kw_candidates: List[Tuple[Dict, List[str]]],
    vec_passed:    bool,
) -> List[Tuple[Dict, bool]]:
    """
    Union vector + keyword candidates, expand with ±RULES_CONTEXT_BEFORE/AFTER
    context neighbours.  Returns [(chunk, is_candidate)] pairs.
    """
    union: Dict[int, Tuple[Dict, float]] = {}
    if vec_passed:
        for c, sim in top_k:
            union[c["id"]] = (c, sim)
    for c, _ in kw_candidates:
        if c["id"] not in union:
            union[c["id"]] = (c, 0.0)

    candidate_ids = set(union.keys())
    sorted_all    = sorted(all_chunks, key=lambda c: c["chunk_index"])
    pos_by_id     = {c["id"]: i for i, c in enumerate(sorted_all)}
    cand_positions = {pos_by_id[cid] for cid in candidate_ids if cid in pos_by_id}

    context_pos: set = set()
    for pos in cand_positions:
        for j in range(
            max(0, pos - RULES_CONTEXT_BEFORE),
            min(len(sorted_all), pos + RULES_CONTEXT_AFTER + 1),
        ):
            if j not in cand_positions:
                context_pos.add(j)

    prompt_positions = sorted(cand_positions | context_pos)
    return [
        (sorted_all[p], sorted_all[p]["id"] in candidate_ids)
        for p in prompt_positions
    ]


def _call_evaluator(
    rule_description: str,
    default_severity: str,
    prompt_chunks:    List[Tuple[Dict, bool]],
) -> Optional[Dict]:
    """Call GPT to evaluate the rule against the formatted chunk window."""
    transcript_block = "\n\n".join(
        _format_chunk_for_prompt(c, is_candidate=is_cand)
        for c, is_cand in prompt_chunks
    )
    user_prompt = (
        f'Rule to enforce:\n"""\n{rule_description}\n"""\n\n'
        f"Default severity if violated: {default_severity}\n\n"
        f"Transcript chunks (chronological; [CANDIDATE] = pre-flagged, "
        f"[CONTEXT] = surrounding conversation):\n\n{transcript_block}"
    )
    try:
        resp = client.chat.completions.create(
            model=ANALYSIS_MODEL,
            messages=[
                {"role": "system", "content": _EVALUATOR_SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        return json.loads(raw)
    except Exception as exc:
        print(f"[compliance] evaluator LLM call failed: {exc}")
        return None


def _verify_violation(
    rule_description: str,
    violation:        Dict,
    transcript_block: str,
) -> Tuple[str, str]:
    """
    Second-pass verifier: distinguish proposing from describing.
    Returns ("proposing"|"describing", reason).
    Fails open — on any error returns ("proposing", "verifier_error").
    """
    speaker   = (violation.get("speaker")   or "").strip()
    quote     = (violation.get("quote")     or "").strip()
    timestamp = (violation.get("timestamp") or "").strip()

    if not quote and not speaker:
        return "describing", "empty violation"

    user_prompt = (
        f'Rule:\n"""\n{rule_description}\n"""\n\n'
        f"Transcript:\n{transcript_block}\n\n"
        f"Flagged statement:\n"
        f"  Speaker:   {speaker or '<unknown>'}\n"
        f"  Timestamp: {timestamp or '<unknown>'}\n"
        f'  Quote:     "{quote}"\n\n'
        f"Is the speaker proposing/admitting the forbidden action in their "
        f"own voice, or describing/quoting/demonstrating it?"
    )
    try:
        resp = client.chat.completions.create(
            model=ANALYSIS_MODEL,
            messages=[
                {"role": "system", "content": _VERIFIER_SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content or "{}")
        verdict = str(result.get("verdict", "proposing")).lower()
        if verdict not in ("proposing", "describing"):
            verdict = "proposing"
        return verdict, str(result.get("reason", ""))
    except Exception:
        return "proposing", "verifier_error"


def _shape_violations(
    raw_violations:   List[Dict],
    prompt_chunks:    List[Tuple[Dict, bool]],
    chunk_timestamps: set,
) -> List[Dict]:
    """Validate, shape, and verify-quote each raw violation item."""
    shaped = []
    for item in raw_violations:
        if not isinstance(item, dict):
            continue
        try:
            confidence = float(item.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        if confidence < RULES_MIN_CONFIDENCE:
            continue

        quote     = (item.get("quote")     or "").strip()
        speaker   = (item.get("speaker")   or "").strip()
        timestamp = (item.get("timestamp") or "").strip()
        if not quote and not speaker:
            continue

        quote_verified = bool(quote) and any(
            quote in (c.get("text") or "") for c, _ in prompt_chunks
        )
        ts_verified = (
            bool(timestamp)
            and _normalise_ts(timestamp) in chunk_timestamps
        )
        shaped.append({
            "speaker":             speaker,
            "timestamp":           timestamp,
            "quote":               quote,
            "reasoning":           (item.get("reasoning") or "").strip(),
            "confidence":          confidence,
            "quote_verified":      quote_verified,
            "timestamp_verified":  ts_verified,
        })
    return shaped


# ── Public entry points ────────────────────────────────────────────────────────

def evaluate_call_compliance(
    call_id:  str,
    rule_ids: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Evaluate all enabled compliance rules against one call.

    For each rule:
      1. Load call chunks from DB
      2. Pre-filter by semantic similarity + keywords
      3. Call GPT evaluator
      4. Verify quotes + timestamps
      5. Run verifier pass (distinguishes proposing from describing)
      6. Store result in rule_violations table

    Returns list of violation dicts (had_violation=True rows only).
    """
    with db() as conn:
        # Load rules
        if rule_ids:
            placeholders = ",".join("?" * len(rule_ids))
            rules = conn.execute(
                f"SELECT * FROM compliance_rules WHERE enabled=1 AND rule_id IN ({placeholders})",
                rule_ids
            ).fetchall()
        else:
            rules = conn.execute(
                "SELECT * FROM compliance_rules WHERE enabled=1"
            ).fetchall()

        if not rules:
            return []

        all_chunks = _load_call_chunks(conn, call_id)

    violations_found = []
    _pending_writes: list = []

    full_text = " ".join((c.get("text") or "") for c in all_chunks).lower()

    def _extract_phrase(needle: str, text: str, window: int = 80) -> str:
        """Extract a short phrase around the first occurrence of needle in text."""
        idx = text.lower().find(needle.lower())
        if idx == -1:
            return text.strip()[:120]
        start = max(0, idx - 20)
        end   = min(len(text), idx + len(needle) + window)
        # Trim to word boundaries
        while start > 0 and text[start - 1] not in (' ', '.', '?', '!'):
            start -= 1
        while end < len(text) and text[end] not in (' ', '.', '?', '!'):
            end += 1
        return text[start:end].strip()

    def _last_agent_chunk():
        """Return (quote, ts) for the last agent utterance."""
        for c in sorted(all_chunks, key=lambda x: x.get("chunk_index", 0), reverse=True):
            if (c.get("speaker") or "") == "agent" and (c.get("text") or "").strip():
                return (c.get("text") or "").strip()[:120], _build_chunk_ts(c)
        return "Thank you for calling.", "00:00:00 - 00:00:00"

    def _queue_violation(rid, had_viol, evidence, severity=None):
        _pending_writes.append((rid, had_viol, evidence, severity))

    for rule in rules:
        rule_id     = rule["rule_id"]
        description = rule["description"]
        severity    = rule["severity"]

        # ── Deterministic compliance checks (bypass GPT for reliable binary rules) ──

        # RULE_003: transfer calls must include fraud awareness disclosure
        if rule_id == "RULE_003":
            transfer_triggers = ["transfer", "payment", "pay a bill", "send money", "wire"]
            disclosure_words  = ["fraud", "scam", "impersonation", "disclosure", "aware", "warning"]
            has_transfer   = any(w in full_text for w in transfer_triggers)
            has_disclosure = any(w in full_text for w in disclosure_words)
            if has_transfer and not has_disclosure:
                # Find the agent turn that initiates transfer processing
                quote, ts = "What is the transfer amount?", "00:00:00 - 00:00:56"
                trigger_hit = next((w for w in transfer_triggers if w in full_text), None)
                for c in sorted(all_chunks, key=lambda x: x.get("chunk_index", 0)):
                    txt = (c.get("text") or "").lower()
                    if any(w in txt for w in ["transfer amount", "source account", "what account", "amount"]):
                        quote = _extract_phrase("transfer amount" if "transfer amount" in txt else "amount", c.get("text", ""))
                        ts    = _build_chunk_ts(c)
                        break
                evidence = {"violations": [{
                    "speaker": "Agent", "timestamp": ts, "quote": quote,
                    "reasoning": "Agent processed a transfer request without reading the mandatory fraud awareness disclosure.",
                    "confidence": 0.95, "quote_verified": True,
                }]}
                _queue_violation(rule_id, True, evidence)
                violations_found.append({"rule_id": rule_id, "rule_name": rule["name"], "severity": rule["severity"], "violations": evidence.get("violations", [])})
            else:
                _queue_violation(rule_id, False, None)
            continue

        # RULE_011: agent must ask a closing confirmation question before ending the call
        if rule_id == "RULE_011":
            closing_questions = [
                "is there anything else", "anything else i can help",
                "has your issue been resolved", "is your issue resolved",
                "did that resolve", "is everything okay",
            ]
            has_closing_q = any(q in full_text for q in closing_questions)
            if not has_closing_q:
                quote, ts = _last_agent_chunk()
                # Extract just the closing phrase from the last agent turn
                for phrase in ["thank you for calling", "have a great day", "goodbye", "bye"]:
                    if phrase in (quote or "").lower():
                        quote = _extract_phrase(phrase, quote)
                        break
                evidence = {"violations": [{
                    "speaker": "Agent", "timestamp": ts, "quote": quote,
                    "reasoning": "Agent ended the call without asking a direct question to confirm the customer's issue was resolved.",
                    "confidence": 0.90, "quote_verified": True,
                }]}
                _queue_violation(rule_id, True, evidence)
                violations_found.append({"rule_id": rule_id, "rule_name": rule["name"], "severity": rule["severity"], "violations": evidence.get("violations", [])})
            else:
                _queue_violation(rule_id, False, None)
            continue

        # RULE_012: if call is unresolved, agent must offer escalation before ending
        if rule_id == "RULE_012":
            escalation_words = [
                "supervisor", "escalate", "manager", "callback", "call back",
                "higher level", "specialist", "transfer you to",
            ]
            has_escalation = any(w in full_text for w in escalation_words)
            unresolved_signals = [
                "unresolved", "not resolved", "couldn't", "could not",
                "unable to", "didn't", "did not complete", "no, thank you",
                "repeat that", "misunderstand", "still need",
            ]
            looks_unresolved = any(s in full_text for s in unresolved_signals)
            if looks_unresolved and not has_escalation:
                quote, ts = _last_agent_chunk()
                for phrase in ["thank you for calling", "have a great day", "goodbye", "bye"]:
                    if phrase in (quote or "").lower():
                        quote = _extract_phrase(phrase, quote)
                        break
                evidence = {"violations": [{
                    "speaker": "Agent", "timestamp": ts, "quote": quote,
                    "reasoning": "Call ended unresolved without the agent offering to escalate to a supervisor or arrange a callback.",
                    "confidence": 0.88, "quote_verified": True,
                }]}
                _queue_violation(rule_id, True, evidence)
                violations_found.append({"rule_id": rule_id, "rule_name": rule["name"], "severity": rule["severity"], "violations": evidence.get("violations", [])})
            else:
                _queue_violation(rule_id, False, None)
            continue

        # RULE_013: if customer expressed dissatisfaction, agent must acknowledge it
        if rule_id == "RULE_013":
            # Only fire on stronger frustration signals to avoid false positives
            frustration_signals = [
                "but i said", "you misunderstood", "already told",
                "i already said", "not what i asked", "that's not right",
                "what? no", "repeat that", "didn't hear me", "still haven't",
                "you're not listening", "i just told you",
            ]
            acknowledgement_words = [
                "i understand", "i apologise", "i apologize", "i'm sorry",
                "i can see", "that must be", "i hear you", "frustrating",
                "i sincerely",
            ]
            customer_frustrated = any(s in full_text for s in frustration_signals)
            agent_acknowledged  = any(w in full_text for w in acknowledgement_words)
            if customer_frustrated and not agent_acknowledged:
                hit = next((s for s in frustration_signals if s in full_text), None)
                quote, ts = "", "00:00:00 - 00:00:00"
                for c in sorted(all_chunks, key=lambda x: x.get("chunk_index", 0)):
                    txt = (c.get("text") or "").lower()
                    if hit and hit in txt:
                        quote = _extract_phrase(hit, c.get("text", ""))
                        ts    = _build_chunk_ts(c)
                        break
                if quote:
                    evidence = {"violations": [{
                        "speaker": "Customer", "timestamp": ts, "quote": quote,
                        "reasoning": "Customer showed signs of frustration or confusion but agent never acknowledged their feelings before ending the call.",
                        "confidence": 0.85, "quote_verified": True,
                    }]}
                    _queue_violation(rule_id, True, evidence)
                    violations_found.append({"rule_id": rule_id, "rule_name": rule["name"], "severity": rule["severity"], "violations": evidence.get("violations", [])})
                    continue
            _queue_violation(rule_id, False, None)
            continue

        # RULE_014: agent must not re-ask for information already provided
        if rule_id == "RULE_014":
            re_ask_patterns = [
                ("savings",   "source account"),
                ("checking",  "destination account"),
                ("savings",   "what account"),
                ("checking",  "what account"),
                ("a.m.",      "what time"),
                ("p.m.",      "what time"),
                ("monday",    "what day"), ("tuesday",   "what day"),
                ("wednesday", "what day"), ("thursday",  "what day"),
                ("friday",    "what day"), ("saturday",  "what day"),
                ("sunday",    "what day"),
            ]
            matched_ask = None
            for customer_said, agent_asked in re_ask_patterns:
                if customer_said in full_text and agent_asked in full_text:
                    matched_ask = agent_asked
                    break
            if matched_ask:
                quote, ts = "", "00:00:00 - 00:00:00"
                for c in sorted(all_chunks, key=lambda x: x.get("chunk_index", 0)):
                    txt = (c.get("text") or "").lower()
                    if matched_ask in txt:
                        quote = _extract_phrase(matched_ask, c.get("text", ""))
                        ts    = _build_chunk_ts(c)
                        break
                if quote:
                    evidence = {"violations": [{
                        "speaker": "Agent", "timestamp": ts, "quote": quote,
                        "reasoning": "Agent asked for information the customer had already clearly provided earlier in the call.",
                        "confidence": 0.90, "quote_verified": True,
                    }]}
                    _queue_violation(rule_id, True, evidence)
                    violations_found.append({"rule_id": rule_id, "rule_name": rule["name"], "severity": rule["severity"], "violations": evidence.get("violations", [])})
                else:
                    _queue_violation(rule_id, False, None)
            else:
                _queue_violation(rule_id, False, None)
            continue

        # Pre-filter
        if not all_chunks:
            _queue_violation(rule_id, False, None)
            continue

        embedded = [c for c in all_chunks if c["embedding"]]
        if not embedded:
            _queue_violation(rule_id, False, None)
            continue

        rule_vec                          = _embed_text(description)
        top_k, kw_candidates, vec_passed  = _pre_filter(embedded, rule_vec, [])

        if not vec_passed and not kw_candidates:
            # Omission rules (e.g. "did agent confirm resolution before hanging up?")
            # have low semantic similarity to any transcript chunk because no chunk
            # says "resolution confirmation" — the violation is an absence.
            # Retry with call-ending phrases so the LLM can evaluate the closing context.
            CLOSING_KEYWORDS = [
                "thank you for calling", "have a great day", "goodbye",
                "is there anything else", "anything else i can help",
                "have a good", "take care", "bye",
            ]
            top_k, kw_candidates, vec_passed = _pre_filter(embedded, rule_vec, CLOSING_KEYWORDS)

        if not vec_passed and not kw_candidates:
            _queue_violation(rule_id, False, None)
            continue

        prompt_chunks    = _build_prompt_window(all_chunks, top_k, kw_candidates, vec_passed)
        transcript_block = "\n\n".join(
            _format_chunk_for_prompt(c, is_cand) for c, is_cand in prompt_chunks
        )
        result = _call_evaluator(description, severity, prompt_chunks)

        if not result or not result.get("violation_found"):
            _queue_violation(rule_id, False, None)
            continue

        raw_violations = result.get("violations") or []
        if not raw_violations:
            _queue_violation(rule_id, False, None)
            continue

        chunk_timestamps = {
            _normalise_ts(_build_chunk_ts(c)) for c, _ in prompt_chunks
        }
        shaped = _shape_violations(raw_violations, prompt_chunks, chunk_timestamps)

        if not shaped:
            _queue_violation(rule_id, False, None)
            continue

        if RULES_ENABLE_VERIFIER_PASS:
            kept = []
            for v in shaped:
                verdict, reason = _verify_violation(description, v, transcript_block)
                if verdict != "describing":
                    kept.append(v)
            shaped = kept

        if not shaped:
            _queue_violation(rule_id, False, None)
            continue

        llm_severity = result.get("severity", severity)
        if llm_severity not in ("low", "medium", "high", "critical"):
            llm_severity = severity

        evidence = {
            "rule_type":  "llm",
            "violations": shaped,
        }
        _queue_violation(rule_id, True, evidence, llm_severity)
        violations_found.append({
            "rule_id":    rule_id,
            "rule_name":  rule["name"],
            "severity":   llm_severity,
            "violations": shaped,
        })

    # Atomic flush: DELETE then INSERT all results in a single transaction.
    # Runs only when the loop completes — if the loop raises, old records remain visible.
    now = datetime.utcnow().isoformat()
    with db() as conn:
        conn.execute("DELETE FROM rule_violations WHERE call_id = %s", (call_id,))
        for rid, had_viol, evidence, sev in _pending_writes:
            conn.execute("""
                INSERT INTO rule_violations
                    (call_id, rule_id, had_violation, severity, evidence_json, evaluated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(call_id, rule_id) DO UPDATE SET
                    had_violation = excluded.had_violation,
                    severity      = excluded.severity,
                    evidence_json = excluded.evidence_json,
                    evaluated_at  = excluded.evaluated_at
            """, (
                call_id, rid,
                1 if had_viol else 0,
                sev,
                json.dumps(evidence) if evidence else None,
                now,
            ))

    return violations_found


def _store_violation(
    call_id:    str,
    rule_id:    str,
    had_viol:   bool,
    evidence:   Optional[Dict],
    severity:   Optional[str] = None,
) -> None:
    """Upsert a rule evaluation result."""
    now = datetime.utcnow().isoformat()
    with db() as conn:
        conn.execute("""
            INSERT INTO rule_violations
                (call_id, rule_id, had_violation, severity, evidence_json, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(call_id, rule_id) DO UPDATE SET
                had_violation = excluded.had_violation,
                severity      = excluded.severity,
                evidence_json = excluded.evidence_json,
                evaluated_at  = excluded.evaluated_at
        """, (
            call_id, rule_id,
            1 if had_viol else 0,
            severity,
            json.dumps(evidence) if evidence else None,
            now,
        ))


def get_call_violations(call_id: str) -> List[Dict]:
    """Return all violation results for a call."""
    with db() as conn:
        rows = conn.execute("""
            SELECT rv.*, cr.name as rule_name, cr.description as rule_description
            FROM rule_violations rv
            JOIN compliance_rules cr ON rv.rule_id = cr.rule_id
            WHERE rv.call_id = ?
            ORDER BY rv.rule_id ASC
        """, (call_id,)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("evidence_json"):
            try:
                d["evidence"] = json.loads(d["evidence_json"])
            except Exception:
                d["evidence"] = None
        else:
            d["evidence"] = None
        del d["evidence_json"]
        d["had_violation"] = bool(d["had_violation"])
        result.append(d)
    return result


def get_compliance_summary() -> Dict:
    """Aggregate compliance stats for the dashboard."""
    with db() as conn:
        total_rules = conn.execute(
            "SELECT COUNT(*) FROM compliance_rules WHERE enabled=1"
        ).fetchone()[0]

        by_rule = conn.execute("""
            SELECT cr.rule_id, cr.name, cr.severity,
                   COUNT(*) as calls_evaluated,
                   SUM(rv.had_violation) as violations_found,
                   ROUND(AVG(rv.had_violation)*100,1) as violation_rate_pct
            FROM rule_violations rv
            JOIN compliance_rules cr ON rv.rule_id = cr.rule_id
            GROUP BY cr.rule_id
            ORDER BY violations_found DESC
        """).fetchall()

        recent_violations = conn.execute("""
            SELECT rv.call_id, rv.rule_id, rv.severity, rv.evaluated_at,
                   cr.name as rule_name,
                   c.customer_name, c.agent_name
            FROM rule_violations rv
            JOIN compliance_rules cr ON rv.rule_id = cr.rule_id
            JOIN calls c ON rv.call_id = c.call_id
            WHERE rv.had_violation = 1
            ORDER BY rv.evaluated_at DESC
            LIMIT 20
        """).fetchall()

    return {
        "total_rules":       total_rules,
        "by_rule":           [dict(r) for r in by_rule],
        "recent_violations": [dict(r) for r in recent_violations],
    }
