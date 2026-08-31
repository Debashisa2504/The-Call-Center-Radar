"""
backend/config.py
------------------
Central configuration — every module imports from here.
All values are driven by environment variables so nothing needs
to be edited in code between dev/prod/test runs.
"""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR     = Path(os.getenv("DATA_DIR",  str(PROJECT_ROOT / "data")))
AUDIO_DIR    = Path(os.getenv("AUDIO_DIR", str(PROJECT_ROOT / "callradar-data" / "audio")))
META_DIR     = Path(os.getenv("META_DIR",  str(PROJECT_ROOT / "callradar-data" / "metadata")))
DATABASE_URL = os.getenv("DATABASE_URL", "")  # postgresql://user:pass@host:5432/callradar

DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── LLM / API keys ────────────────────────────────────────────────────────────
OPENAI_API_KEY         = os.getenv("OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT  = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "gpt-4o-mini")
EMBED_MODEL    = os.getenv("EMBED_MODEL",    "text-embedding-3-small")
WHISPER_MODEL  = os.getenv("WHISPER_MODEL",  "whisper-1")


def make_openai_client():
    """Return AzureOpenAI if AZURE_OPENAI_ENDPOINT is set, else standard OpenAI."""
    if AZURE_OPENAI_ENDPOINT:
        from openai import AzureOpenAI
        return AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    from openai import OpenAI
    return OpenAI(api_key=OPENAI_API_KEY)

# ── Ghost resolution ──────────────────────────────────────────────────────────
# Customer calls back within N minutes = failed resolution
GHOST_WINDOW_MIN = int(os.getenv("GHOST_WINDOW_MIN", "30"))

# ── Trend clustering ──────────────────────────────────────────────────────────
TREND_CLUSTERS = int(os.getenv("TREND_CLUSTERS", "12"))

# ── Chunking constants (from CortexV — pause-gap boundary chunking) ───────────
# Max utterances before forcing a chunk boundary
CHUNK_MAX_UTTERANCES = int(os.getenv("CHUNK_MAX_UTTERANCES", "15"))
# Max span in seconds before forcing a boundary
CHUNK_MAX_SPAN_SEC = int(os.getenv("CHUNK_MAX_SPAN_SEC", "60"))
# Max word count before forcing a boundary
CHUNK_MAX_WORDS = int(os.getenv("CHUNK_MAX_WORDS", "400"))
# Soft minimum utterances before a pause-gap break is allowed
CHUNK_SOFT_MIN_UTTERANCES = int(os.getenv("CHUNK_SOFT_MIN_UTTERANCES", "3"))
# Soft minimum span before a pause-gap break is allowed
CHUNK_SOFT_MIN_SPAN_SEC = int(os.getenv("CHUNK_SOFT_MIN_SPAN_SEC", "10"))
# Silence gap in seconds that triggers a chunk boundary
CHUNK_PAUSE_GAP_SEC = float(os.getenv("CHUNK_PAUSE_GAP_SEC", "3.0"))
# Word overlap carried into the next chunk for long-monologue splits
CHUNK_OVERLAP_WORDS = int(os.getenv("CHUNK_OVERLAP_WORDS", "40"))
# Same-speaker merge ceiling in seconds
CHUNK_MERGE_GAP_SEC = float(os.getenv("CHUNK_MERGE_GAP_SEC", "1.0"))

# ── Contextual retrieval (CortexV free-layer enrichment) ─────────────────────
# When True, prepends call metadata to each chunk's embedding text
CONTEXT_ENRICHMENT = os.getenv("CONTEXT_ENRICHMENT", "true").lower() in ("1","true","yes","on")
# When True, also calls GPT to generate a per-chunk topic sentence (costs ~$1 extra)
CONTEXT_LLM_ENRICHMENT = os.getenv("CONTEXT_LLM_ENRICHMENT", "false").lower() in ("1","true","yes","on")

# ── Cross-encoder reranker (CortexV) ─────────────────────────────────────────
RERANKER_MODEL    = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANKER_ENABLED  = os.getenv("RERANKER_ENABLED", "true").lower() in ("1","true","yes","on")
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "30"))
RERANK_TOP_K      = int(os.getenv("RERANK_TOP_K", "10"))
DEDUP_THRESHOLD   = float(os.getenv("DEDUP_THRESHOLD", "0.85"))

# ── Compliance rules ──────────────────────────────────────────────────────────
RULES_PRE_FILTER_TOP_K     = int(os.getenv("RULES_PRE_FILTER_TOP_K", "10"))
RULES_PRE_FILTER_MIN_SIM   = float(os.getenv("RULES_PRE_FILTER_MIN_SIM", "0.30"))
RULES_MIN_CONFIDENCE       = float(os.getenv("RULES_MIN_CONFIDENCE", "0.60"))
RULES_CONTEXT_BEFORE       = int(os.getenv("RULES_CONTEXT_BEFORE", "1"))
RULES_CONTEXT_AFTER        = int(os.getenv("RULES_CONTEXT_AFTER", "1"))
RULES_ENABLE_VERIFIER_PASS = os.getenv("RULES_ENABLE_VERIFIER_PASS", "true").lower() in ("1","true","yes","on")

# ── Parallel ingest (PostgreSQL supports concurrent writes; SQLite does not) ──
INGEST_WORKERS = int(os.getenv("INGEST_WORKERS", "1" if not os.getenv("DATABASE_URL") else "5"))

# ── API server ────────────────────────────────────────────────────────────────
API_HOST     = os.getenv("API_HOST", "127.0.0.1")
API_PORT     = int(os.getenv("API_PORT", "8000"))
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
).split(",")
