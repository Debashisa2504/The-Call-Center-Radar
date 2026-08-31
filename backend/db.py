"""
backend/db.py
--------------
Database layer — PostgreSQL only (psycopg2 + pgvector).

The PGConn wrapper makes psycopg2 look like sqlite3 to callers, so the
rest of the codebase can use sqlite3-style code (conn.execute(sql, params),
row["key"] / row[0] access, ? placeholders auto-converted to %s):
  - context manager commits on exit, rolls back on exception
"""
from __future__ import annotations


from contextlib import contextmanager
from typing import Any, Iterator, List, Optional

from .config import DATABASE_URL


# ─────────────────────────────────────────────────────────────────────────────
# Compatibility row wrapper (PostgreSQL path)
# ─────────────────────────────────────────────────────────────────────────────

class PGRow:
    """Dict-like row that also supports integer index access like sqlite3.Row."""
    __slots__ = ("_d", "_keys")

    def __init__(self, row: dict) -> None:
        self._d    = row
        self._keys = list(row.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._d[self._keys[key]]
        return self._d[key]

    def __contains__(self, key) -> bool:
        return key in self._d

    def get(self, key, default=None):
        return self._d.get(key, default)

    def keys(self):
        return self._keys

    def __iter__(self):
        return iter(self._d.values())

    def __repr__(self):
        return f"PGRow({self._d})"


class PGCursor:
    """Wraps a psycopg2 RealDictCursor so fetchone/fetchall return PGRow objects."""
    __slots__ = ("_cur",)

    def __init__(self, cur) -> None:
        self._cur = cur

    def fetchone(self) -> Optional[PGRow]:
        row = self._cur.fetchone()
        return PGRow(dict(row)) if row else None

    def fetchall(self) -> List[PGRow]:
        return [PGRow(dict(r)) for r in self._cur.fetchall()]

    def __iter__(self):
        for row in self._cur:
            yield PGRow(dict(row))

    @property
    def rowcount(self):
        return self._cur.rowcount


class PGConn:
    """
    Wraps a psycopg2 connection to provide a sqlite3-compatible interface.
    Auto-converts ? placeholders to %s and wraps rows in PGRow.
    """
    __slots__ = ("_conn",)

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql: str, params=()) -> PGCursor:
        import psycopg2.extras
        sql = sql.replace("?", "%s")
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return PGCursor(cur)

    def executemany(self, sql: str, params_list) -> None:
        sql = sql.replace("?", "%s")
        cur = self._conn.cursor()
        cur.executemany(sql, params_list)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Connection factory
# ─────────────────────────────────────────────────────────────────────────────

def _pg_conn() -> PGConn:
    import psycopg2
    from pgvector.psycopg2 import register_vector
    conn = psycopg2.connect(DATABASE_URL)
    register_vector(conn)
    return PGConn(conn)





def get_conn():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. This project requires PostgreSQL — "
            "see README Prerequisites."
        )
    return _pg_conn()


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Schema — PostgreSQL DDL
# ─────────────────────────────────────────────────────────────────────────────

_PG_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS calls (
    call_id                 TEXT PRIMARY KEY,
    customer_name           TEXT NOT NULL,
    agent_name              TEXT NOT NULL,
    start_time_ms           BIGINT,
    end_time_ms             BIGINT,
    duration_s              DOUBLE PRECISION,
    audio_path              TEXT,
    session                 TEXT,
    caller_mos              DOUBLE PRECISION,
    agent_mos               DOUBLE PRECISION,
    lhvb_script             DOUBLE PRECISION,
    partner_rating          INTEGER,
    ease_of_connection      INTEGER,

    intent                  TEXT,
    mood_start              TEXT,
    mood_shift              INTEGER DEFAULT 0,
    mood_shift_time_s       DOUBLE PRECISION,
    mood_shift_quote        TEXT,
    mood_shift_direction    TEXT,
    transcript_resolved     INTEGER DEFAULT 0,
    summary                 TEXT,
    attention_score         INTEGER DEFAULT 0,
    attention_reason        TEXT,

    sentiment_score         DOUBLE PRECISION,
    sentiment_label         TEXT,
    emotion_scores_json     TEXT,
    dominant_emotion        TEXT,
    sentiment_summary       TEXT,
    agent_sentiment_json    TEXT,
    customer_sentiment_json TEXT,

    ghost_resolved          INTEGER DEFAULT 0,
    ghost_callback_id       TEXT,
    ghost_gap_min           DOUBLE PRECISION,
    behavioural_resolved    INTEGER DEFAULT 0,
    sequence_resolved       INTEGER,

    trend_cluster           TEXT,
    trend_label             TEXT,

    processed               INTEGER DEFAULT 0,
    processed_at            TEXT
);

-- Backfill for databases created before sequence_resolved existed.
-- Idempotent: no-ops if the column is already present.
ALTER TABLE calls ADD COLUMN IF NOT EXISTS sequence_resolved INTEGER;

CREATE INDEX IF NOT EXISTS idx_calls_customer ON calls(customer_name);
CREATE INDEX IF NOT EXISTS idx_calls_agent    ON calls(agent_name);
CREATE INDEX IF NOT EXISTS idx_calls_session  ON calls(session);

CREATE TABLE IF NOT EXISTS turns (
    id          SERIAL PRIMARY KEY,
    call_id     TEXT NOT NULL REFERENCES calls(call_id),
    speaker     TEXT NOT NULL,
    start_s     DOUBLE PRECISION NOT NULL,
    end_s       DOUBLE PRECISION NOT NULL,
    text        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_call ON turns(call_id);

CREATE TABLE IF NOT EXISTS evidence (
    id              SERIAL PRIMARY KEY,
    call_id         TEXT NOT NULL REFERENCES calls(call_id),
    judgment_type   TEXT NOT NULL,
    timestamp_s     DOUBLE PRECISION NOT NULL,
    quote           TEXT NOT NULL,
    reasoning       TEXT
);
CREATE INDEX IF NOT EXISTS idx_evidence_call ON evidence(call_id);

CREATE TABLE IF NOT EXISTS trends (
    cluster_id      TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    call_count      INTEGER DEFAULT 0,
    example_intents TEXT,
    computed_at     TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id              SERIAL PRIMARY KEY,
    call_id         TEXT NOT NULL REFERENCES calls(call_id),
    chunk_index     INTEGER NOT NULL,
    speaker         TEXT,
    start_s         DOUBLE PRECISION NOT NULL,
    end_s           DOUBLE PRECISION NOT NULL,
    text            TEXT NOT NULL,
    contextual_text TEXT,
    embedding       vector(3072)
);
CREATE INDEX IF NOT EXISTS idx_chunks_call ON chunks(call_id);

CREATE TABLE IF NOT EXISTS compliance_rules (
    rule_id         TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'medium',
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS rule_violations (
    id              SERIAL PRIMARY KEY,
    call_id         TEXT NOT NULL REFERENCES calls(call_id),
    rule_id         TEXT NOT NULL REFERENCES compliance_rules(rule_id),
    had_violation   INTEGER NOT NULL DEFAULT 0,
    severity        TEXT,
    evidence_json   TEXT,
    evaluated_at    TEXT,
    UNIQUE(call_id, rule_id)
);
CREATE INDEX IF NOT EXISTS idx_violations_call ON rule_violations(call_id);
"""

def init_db() -> None:
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. This project requires PostgreSQL — "
            "see README Prerequisites."
        )
    import psycopg2
    from pgvector.psycopg2 import register_vector
    conn = psycopg2.connect(DATABASE_URL)
    register_vector(conn)
    try:
        cur = conn.cursor()
        for stmt in _PG_SCHEMA.split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cur.execute(stmt)
                conn.commit()
            except Exception as e:
                conn.rollback()
                if "already exists" not in str(e):
                    raise
    finally:
        conn.close()