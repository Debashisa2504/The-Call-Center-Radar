"""
backend/pipeline/ingest.py
============================
Main ingestion orchestrator — the only file you need to run.

Pipeline steps (in order)
--------------------------
1.  Load metadata JSON (customer name, agent name, timestamps)
2.  Dual-channel transcription (ffmpeg split → Whisper API per channel)
3.  Pause-gap boundary chunking with free-layer contextual enrichment
4.  Call analysis — citation-first + 7-emotion sentiment (one GPT call)
5.  Embed chunks via OpenAI embeddings API
6.  Store all data in PostgreSQL
7.  [post-all] Ghost resolution detection (pure SQL)
8.  [post-all] Intent clustering + trend labelling
9.  [post-all] Compliance rule evaluation (LLM-as-judge per rule per call)

Idempotent: calls with processed=1 are skipped unless --force is passed.
Ghost detection and compliance evaluation can be re-run independently.

Usage
-----
    python -m backend.pipeline.ingest --all
    python -m backend.pipeline.ingest --all --limit 10   # test run
    python -m backend.pipeline.ingest --call <call_id>
    python -m backend.pipeline.ingest --ghost-only
    python -m backend.pipeline.ingest --trends-only
    python -m backend.pipeline.ingest --compliance-only  # re-evaluate rules
    python -m backend.pipeline.ingest --all --force      # re-process everything
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from ..config import AUDIO_DIR, META_DIR, EMBED_MODEL, INGEST_WORKERS, make_openai_client
from ..db import db, init_db
from .transcribe import transcribe_call
from .analyse    import analyse_call
from .ghost      import compute_ghost_resolutions, get_agent_ghost_rates
from .trends     import compute_trends
from .compliance import (
    seed_default_rules, evaluate_call_compliance, get_compliance_summary
)
from .suggestions import generate_call_suggestions

client = make_openai_client()


# ── Embedding helpers ──────────────────────────────────────────────────────────

def _embed_chunks(chunks, batch_size: int = 100) -> List[List[float]]:
    """Embed chunk contextual_text strings in batches."""
    texts = [c.contextual_text or c.text for c in chunks]
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i: i + batch_size]
        resp  = client.embeddings.create(model=EMBED_MODEL, input=batch)
        embeddings.extend([d.embedding for d in resp.data])
    return embeddings


# ── Metadata helpers ───────────────────────────────────────────────────────────

def _load_metadata(call_id: str) -> Optional[dict]:
    path = META_DIR / f"{call_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _customer_name(meta: dict) -> str:
    return meta.get("caller", {}).get(
        "metadata", {}
    ).get("first and last name", "Unknown")


def _agent_name(meta: dict) -> str:
    return meta.get("agent", {}).get(
        "metadata", {}
    ).get("agent_name", "Unknown")


def _call_date(meta: dict) -> str:
    ms = meta.get("start_time_ms", 0)
    if ms:
        from datetime import datetime
        return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")
    return ""


# ── Storage ────────────────────────────────────────────────────────────────────

def _store_call(
    conn, call_id: str, meta: dict, turns: list,
    analysis: dict, chunks, embeddings: list
) -> None:
    caller        = meta.get("caller", {})
    agent         = meta.get("agent",  {})
    labels        = meta.get("labels", {})
    caller_survey = (caller.get("survey_response") or {}).get("data") or {}

    start_ms = meta.get("start_time_ms", 0)
    end_ms   = meta.get("end_time_ms",   0)
    duration = (end_ms - start_ms) / 1000 if end_ms > start_ms else 0

    def safe_int(v):
        try: return int(v)
        except: return None

    # Extract 7-emotion sentiment data
    sentiment = analysis.get("sentiment", {})
    overall   = sentiment.get("overall", {})
    ag_sent   = sentiment.get("agent", {})
    cu_sent   = sentiment.get("customer", {})

    conn.execute("""
        INSERT INTO calls (
            call_id, customer_name, agent_name,
            start_time_ms, end_time_ms, duration_s,
            audio_path, session,
            caller_mos, agent_mos, lhvb_script,
            partner_rating, ease_of_connection,
            intent, mood_start, mood_shift,
            mood_shift_time_s, mood_shift_quote, mood_shift_direction,
            transcript_resolved, summary,
            attention_score, attention_reason,
            sentiment_score, sentiment_label, emotion_scores_json,
            dominant_emotion, sentiment_summary,
            agent_sentiment_json, customer_sentiment_json,
            processed, processed_at
        ) VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
        ON CONFLICT (call_id) DO UPDATE SET
            customer_name=EXCLUDED.customer_name,
            agent_name=EXCLUDED.agent_name,
            start_time_ms=EXCLUDED.start_time_ms,
            end_time_ms=EXCLUDED.end_time_ms,
            duration_s=EXCLUDED.duration_s,
            audio_path=EXCLUDED.audio_path,
            session=EXCLUDED.session,
            caller_mos=EXCLUDED.caller_mos,
            agent_mos=EXCLUDED.agent_mos,
            lhvb_script=EXCLUDED.lhvb_script,
            partner_rating=EXCLUDED.partner_rating,
            ease_of_connection=EXCLUDED.ease_of_connection,
            intent=EXCLUDED.intent,
            mood_start=EXCLUDED.mood_start,
            mood_shift=EXCLUDED.mood_shift,
            mood_shift_time_s=EXCLUDED.mood_shift_time_s,
            mood_shift_quote=EXCLUDED.mood_shift_quote,
            mood_shift_direction=EXCLUDED.mood_shift_direction,
            transcript_resolved=EXCLUDED.transcript_resolved,
            summary=EXCLUDED.summary,
            attention_score=EXCLUDED.attention_score,
            attention_reason=EXCLUDED.attention_reason,
            sentiment_score=EXCLUDED.sentiment_score,
            sentiment_label=EXCLUDED.sentiment_label,
            emotion_scores_json=EXCLUDED.emotion_scores_json,
            dominant_emotion=EXCLUDED.dominant_emotion,
            sentiment_summary=EXCLUDED.sentiment_summary,
            agent_sentiment_json=EXCLUDED.agent_sentiment_json,
            customer_sentiment_json=EXCLUDED.customer_sentiment_json,
            processed=EXCLUDED.processed,
            processed_at=EXCLUDED.processed_at
    """, (
        call_id,
        _customer_name(meta),
        _agent_name(meta),
        start_ms, end_ms, duration,
        str(AUDIO_DIR / f"{call_id}.mp3"),
        meta.get("session"),
        labels.get("caller_mos"),
        labels.get("agent_mos"),
        labels.get("lhvb_script"),
        safe_int(caller_survey.get("partner_rating")),
        safe_int(caller_survey.get("ease_of_connection")),
        # Core analysis
        analysis.get("intent"),
        analysis.get("mood_start"),
        1 if analysis.get("mood_shift") else 0,
        analysis.get("mood_shift_timestamp_s"),
        analysis.get("mood_shift_quote"),
        analysis.get("mood_shift_direction"),
        1 if analysis.get("transcript_resolved") else 0,
        analysis.get("summary"),
        analysis.get("attention_score", 0),
        analysis.get("attention_reason"),
        # 7-emotion sentiment
        overall.get("score"),
        overall.get("label"),
        json.dumps(cu_sent.get("emotion_scores", {})),
        cu_sent.get("dominant_emotion"),
        overall.get("summary"),
        json.dumps(ag_sent),
        json.dumps(cu_sent),
        1,
        datetime.utcnow().isoformat(),
    ))

    # Turns (flat transcript for the UI)
    conn.execute("DELETE FROM turns WHERE call_id=?", (call_id,))
    for t in turns:
        conn.execute("""
            INSERT INTO turns (call_id, speaker, start_s, end_s, text)
            VALUES (?,?,?,?,?)
        """, (call_id, t["speaker"], t["start_s"], t["end_s"], t["text"]))

    # Evidence citations
    conn.execute("DELETE FROM evidence WHERE call_id=?", (call_id,))
    _store_evidence(conn, call_id, analysis)

    # Chunks with embeddings
    conn.execute("DELETE FROM chunks WHERE call_id=?", (call_id,))
    from ..config import DATABASE_URL
    for chunk, embedding in zip(chunks, embeddings):
        emb_val = embedding
        conn.execute("""
            INSERT INTO chunks
                (call_id, chunk_index, speaker, start_s, end_s,
                 text, contextual_text, embedding)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            call_id,
            chunk.chunk_index,
            chunk.speaker,
            chunk.start_s,
            chunk.end_s,
            chunk.text,
            chunk.contextual_text,
            emb_val,
        ))


def _store_evidence(conn, call_id: str, analysis: dict) -> None:
    def add(jtype: str, ts, quote, reasoning=""):
        if ts is None or not quote:
            return
        conn.execute("""
            INSERT INTO evidence (call_id, judgment_type, timestamp_s, quote, reasoning)
            VALUES (?,?,?,?,?)
        """, (call_id, jtype, float(ts), str(quote), str(reasoning)))

    ie = analysis.get("intent_evidence") or {}
    add("intent", ie.get("timestamp_s"), ie.get("quote"))

    if analysis.get("mood_shift"):
        add("mood_shift",
            analysis.get("mood_shift_timestamp_s"),
            analysis.get("mood_shift_quote"),
            analysis.get("mood_shift_direction", ""))

    re_ = analysis.get("resolved_evidence") or {}
    add("resolved", re_.get("timestamp_s"), re_.get("quote"))

    for km in (analysis.get("key_moments") or []):
        add("key_moment", km.get("timestamp_s"), km.get("quote"), km.get("label", ""))


# ── Single call ingestion ─────────────────────────────────────────────────────

def ingest_one(call_id: str, force: bool = False) -> bool:
    """Ingest a single call. Returns True on success, False on skip/error."""
    meta = _load_metadata(call_id)
    if not meta:
        print(f"  [SKIP] No metadata: {call_id}")
        return False

    if not force:
        with db() as conn:
            row = conn.execute(
                "SELECT processed FROM calls WHERE call_id=?", (call_id,)
            ).fetchone()
            if row and row["processed"]:
                print(f"  [SKIP] Already processed: {call_id}")
                return False

    audio_path = AUDIO_DIR / f"{call_id}.mp3"
    if not audio_path.exists():
        print(f"  [SKIP] No audio: {call_id}")
        return False

    print(f"  [PROCESS] {call_id}")
    try:
        agent    = _agent_name(meta)
        customer = _customer_name(meta)
        date_str = _call_date(meta)

        # Step 2-3: transcribe + chunk (with contextual enrichment)
        turns, chunks = transcribe_call(
            audio_path,
            agent_name=agent,
            customer_name=customer,
            call_date=date_str,
        )

        # Step 4: analyse (citation-first + 7-emotion sentiment)
        analysis = analyse_call(turns, call_id)

        # Step 5: embed chunks
        embeddings = _embed_chunks(chunks) if chunks else []

        # Step 6: store everything
        with db() as conn:
            _store_call(conn, call_id, meta, turns, analysis, chunks, embeddings)

        print(
            f"    turns={len(turns)}  chunks={len(chunks)}  "
            f"emotion={analysis.get('sentiment',{}).get('customer',{}).get('dominant_emotion','?')}  "
            f"intent={analysis.get('intent','')[:50]}"
        )
        return True

    except Exception:
        print(f"  [ERROR] {call_id}")
        traceback.print_exc()
        return False


# ── Bulk ingestion ─────────────────────────────────────────────────────────────

def ingest_all(force: bool = False, limit: Optional[int] = None) -> None:
    """Ingest every call in META_DIR, then run post-processing."""
    init_db()
    seed_default_rules()

    call_ids = sorted(p.stem for p in META_DIR.glob("*.json"))
    if limit:
        call_ids = call_ids[:limit]

    print(f"Ingesting {len(call_ids)} calls with {INGEST_WORKERS} worker(s)…")
    ok = skip = 0

    if INGEST_WORKERS > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=INGEST_WORKERS) as pool:
            futures = {pool.submit(ingest_one, cid, force): cid for cid in call_ids}
            for future in as_completed(futures):
                if future.result():
                    ok += 1
                else:
                    skip += 1
                total_done = ok + skip
                if total_done % 50 == 0:
                    print(f"  Progress: {total_done}/{len(call_ids)} calls")
    else:
        for call_id in call_ids:
            if ingest_one(call_id, force=force):
                ok += 1
            else:
                skip += 1

    print(f"\nDone: {ok} processed, {skip} skipped")

    print("\nRunning ghost resolution detection…")
    ghosts = compute_ghost_resolutions()
    print(f"  Ghost resolutions: {ghosts}")

    print("\nRunning intent clustering…")
    clusters = compute_trends()
    print(f"  Clusters: {clusters}")

    print("\nRunning compliance evaluation…")
    _run_compliance_all()

    print("\nIngestion complete.")


def _run_compliance_all() -> None:
    """Evaluate all enabled rules against all processed calls."""
    with db() as conn:
        call_ids = [
            r[0] for r in conn.execute(
                "SELECT call_id FROM calls WHERE processed=1"
            ).fetchall()
        ]

    total_violations = 0
    for call_id in call_ids:
        try:
            violations = evaluate_call_compliance(call_id)
            total_violations += len(violations)
        except Exception:
            pass

    summary = get_compliance_summary()
    print(
        f"  Evaluated {len(call_ids)} calls — "
        f"{total_violations} violation events found"
    )
    for row in summary.get("by_rule", []):
        if row["violations_found"]:
            print(
                f"    {row['rule_id']} {row['name']}: "
                f"{row['violations_found']} violations "
                f"({row['violation_rate_pct']}% of calls)"
            )


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Call Radar ingestion pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m backend.pipeline.ingest --all           # full pipeline
  python -m backend.pipeline.ingest --all --limit 5 # test with 5 calls
  python -m backend.pipeline.ingest --call abc123   # single call
  python -m backend.pipeline.ingest --ghost-only    # recompute ghost scores
  python -m backend.pipeline.ingest --compliance-only # re-evaluate rules
"""
    )
    parser.add_argument("--all",              action="store_true", help="Ingest all calls")
    parser.add_argument("--call",             type=str,            help="Ingest one call ID")
    parser.add_argument("--force",            action="store_true", help="Re-ingest processed calls")
    parser.add_argument("--limit",            type=int,            help="Max calls (for testing)")
    parser.add_argument("--ghost-only",       action="store_true", help="Recompute ghost resolutions only")
    parser.add_argument("--trends-only",      action="store_true", help="Recompute intent clusters only")
    parser.add_argument("--compliance-only",  action="store_true", help="Re-evaluate compliance rules only")
    args = parser.parse_args()

    init_db()
    seed_default_rules()

    if args.ghost_only:
        n = compute_ghost_resolutions()
        print(f"Ghost resolutions: {n}")
        for row in get_agent_ghost_rates():
            print(f"  {row['agent_name']}: {row['ghost_rate']*100:.1f}% ghost rate")
        return

    if args.trends_only:
        n = compute_trends()
        print(f"Clusters: {n}")
        return

    if args.compliance_only:
        _run_compliance_all()
        return

    if args.all:
        ingest_all(force=args.force, limit=args.limit)
    elif args.call:
        ingest_one(args.call, force=args.force)
        compute_ghost_resolutions()
        evaluate_call_compliance(args.call)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
