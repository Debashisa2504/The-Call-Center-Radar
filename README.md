# Call Radar — Ghost Resolution Intelligence

> "Everyone else tells you what happened on the call. We tell you what happened after."

**Team: Ghost Hunters** — Debashisa Behera · Aakansha Sharma
Call-Centre Analytics Hackathon 2026

---

## 1. The Problem

Call centres generate hundreds of recordings a day. Existing tools transcribe them, score sentiment, and produce dashboards — but they analyse every call in isolation. None of them connect one call to the next.

**Our insight:** if an agent marks a call "resolved" and the same customer calls back within 30 minutes, the resolution was false. We call this a **Ghost Resolution**.

Finding this requires cross-call analysis: matching calls by customer identity and comparing timestamps. Generic transcript/sentiment tools miss it entirely.

| Signal | Generic Tool | Call Radar |
|---|---|---|
| Transcript | ✓ | ✓ |
| Intent, mood, resolution | ✓ | ✓ |
| **Ghost resolution detection** | ✗ | ✓ cross-call SQL self-join |
| **Behavioural resolution** (actual, not claimed) | ✗ | ✓ callback = failure |
| **Customer frustration trajectory** | ✗ | ✓ mood arc across calls |
| **Agent ghost-rate leaderboard** | ✗ | ✓ |
| **Per-channel speaker attribution** | ✗ | ✓ no diarization needed |
| **Mono audio detection** | ✗ | ✓ RMS check + speaker alternation |
| **Evidence citations** (timestamp + verbatim quote) | ✗ | ✓ every judgment cited |
| **Compliance rule engine** | ✗ | ✓ 3-stage: pre-filter → judge → verify |
| **7-emotion sentiment** | ✗ | ✓ per-speaker emotion vector |
| **Customer perception dashboard** | ✗ | ✓ issue frequency + satisfaction |

---

## 2. The Ghost Resolution Concept

A Ghost Resolution occurs when two conditions hold simultaneously:

1. The transcript analysis says the agent claimed the issue was resolved (`transcript_resolved = true`)
2. The same customer calls back within 30 minutes (`ghost_resolved = true`)

When both are true, the agent's claim was false — the customer's own behaviour is the ground truth, which is stronger evidence than any sentiment score.

**Behavioural resolution** (`behavioural_resolved = true`) = transcript-resolved and no callback within the window = the issue was genuinely fixed.

The gap between the claimed resolution rate and the behavioural resolution rate is the single most actionable metric in a contact centre.

Detection is a pure SQL self-join — zero API cost, re-runnable at any time, completes in under a second across thousands of calls:

```sql
UPDATE calls SET ghost_resolved = 1
WHERE transcript_resolved = 1 AND EXISTS (
  SELECT 1 FROM calls c2
  WHERE c2.customer_name = calls.customer_name
    AND c2.start_time_ms > calls.end_time_ms
    AND c2.start_time_ms < calls.end_time_ms + 1800000
);
```

---

## 3. Architecture

Three components communicate only through PostgreSQL — the frontend and backend never share state directly.

```
Audio (.mp3, stereo)                  Frontend
  ├─ agent   = left channel           React + Vite + Tailwind
  └─ customer = right channel         Dashboard · Customers · Call Detail
         │                                    ▲
         ▼                                    │ REST (JSON)
  Ingestion Pipeline  ──────────────►  FastAPI Backend
  (backend/pipeline/)                  (backend/main.py)
         │                                    ▲
         └────────────────────────────────────┘
                   PostgreSQL + pgvector
```

### Ingestion Pipeline — Step by Step

| Step | Module | What it does |
|---|---|---|
| 1. Transcription | `pipeline/transcribe.py` | ffmpeg splits each stereo MP3 into two mono channels (agent = left, customer = right). Each channel is sent to Whisper independently — no diarization needed. For mono recordings (customer channel RMS < 0.01), the system transcribes once and assigns speakers by alternating on pause gaps > 1 s. |
| 2. Citation-first analysis | `pipeline/analyse.py` | A single GPT call returns structured JSON: intent, mood_start, mood_shift (with timestamp), transcript_resolved, attention score (0–100), a ≤40-word summary, and a 7-emotion vector per speaker. Every judgment is paired with an evidence field (timestamp + verbatim quote); if no evidence exists, the model must return null/0 rather than guess. |
| 3. Ghost detection | `pipeline/ghost.py` | Pure SQL self-join (see above). Zero API cost, re-runnable independently via `--ghost-only`. |
| 4. Trend clustering | `pipeline/trends.py` | Each call's intent string is embedded and clustered with k-means; each cluster is labelled by GPT and surfaced in the Trends tab. |
| 5. Compliance evaluation | `pipeline/compliance.py` | 3-stage LLM judge — see below. |
| 6. Follow-up suggestions | `pipeline/suggestions.py` | Generates per-call follow-up questions for agents and QA reviewers. |

### Compliance Engine — 3-Stage Design

Designed to prevent GPT from hallucinating violations that get surfaced to a manager:

1. **Pre-filter** — embed the rule; retrieve top-K semantically similar transcript chunks via cosine similarity, re-ranked by a cross-encoder. Keyword hits bypass the similarity floor.
2. **LLM judge** — GPT is shown only those chunks and asked whether the rule was violated, with a required citation (speaker, timestamp, exact quote).
3. **Verifier** — the cited quote is checked as a verbatim substring of the transcript at the cited timestamp. If it doesn't match, the violation is dropped and not surfaced.

Five of the 14 rules (re-asked information, missing closing question, missing escalation offer, missing fraud disclosure, missing frustration acknowledgement) are deterministic keyword/pattern checks rather than LLM calls — these proved more reliable and cheaper than asking GPT to detect an absence.

Rule evaluation writes atomically: results are DELETE + INSERT'd in a single transaction after all rules finish, so a mid-evaluation crash never leaves partial results.

### Database

PostgreSQL + pgvector. Data is written only during ingestion — every API endpoint is read-only.

| Table | Purpose |
|---|---|
| `calls` | One row per call — analysis, ghost/behavioural resolution, sentiment, timing |
| `turns` | Transcript speaker turns: speaker, start_s, end_s, text |
| `chunks` | Embedded chunks for semantic search: `embedding vector(3072)` |
| `evidence` | Citation triplets: `(judgment_type, timestamp_s, quote, reasoning)` |
| `trends` | Intent cluster labels from k-means |
| `compliance_rules` | Configurable rules: name, description, severity, enabled |
| `rule_violations` | Per-call rule results: `(call_id, rule_id, had_violation, severity, evidence_json)` |

---

## 4. Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + PostgreSQL + pgvector |
| AI | Azure OpenAI — gpt-4o-mini (analysis, compliance judge, cluster labelling), text-embedding-3-small (embeddings), whisper-1 (transcription) |
| Frontend | React + Vite + Tailwind CSS |
| Audio | ffmpeg via `imageio-ffmpeg` — bundled, **no system install required** |

---

## 5. Setup

### Prerequisites

- Python 3.11+
- Node.js 20+ (18+ also works)
- Azure OpenAI account with `gpt-4o`, `text-embedding-3-large` (or `3-small`), and `whisper` deployments
- PostgreSQL with the pgvector extension (`CREATE EXTENSION vector`) — required; the app fails fast on startup if `DATABASE_URL` isn't set

### Steps

```bash
# 1. Clone and enter the repo
git clone https://github.com/Debashisa2504/The-Call-Center-Radar.git
cd The-Call-Center-Radar

# 2. Place call recordings so the layout is:
#    callradar/callradar-data/audio/     ← .mp3 files (stereo: left=agent, right=customer)
#    callradar/callradar-data/metadata/  ← .json files (one per call, same name as the mp3)
#
# Each metadata JSON must have at minimum:
#   call_id, agent_name, customer_name, start_time_ms, end_time_ms

# 3. Python environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt   # includes imageio-ffmpeg — no system ffmpeg needed

# 4. Create a .env file in the project root (see .env.example for all options):
DATABASE_URL=postgresql://user:password@host:5432/callradar
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
OPENAI_API_KEY=<your-key>
AZURE_OPENAI_API_VERSION=2024-12-01-preview
ANALYSIS_MODEL=gpt-4o-mini
EMBED_MODEL=text-embedding-3-small
WHISPER_MODEL=whisper-1
GHOST_WINDOW_MIN=30
INGEST_WORKERS=2

# 5. Initialise the database schema (safe to re-run — all statements are IF NOT EXISTS)
python scripts/init_schema.py

# 6. Frontend packages
cd frontend && npm install && cd ..
```

---

## 6. Running the System

### Step 1 — Ingest calls

Processes raw MP3s into transcripts, analysis, ghost flags, trends, and compliance results (~2 min per call at default settings).

```bash
# Test with a small batch first
python -m backend.pipeline.ingest --all --limit 3

# Full ingest — processes everything in callradar-data/
python -m backend.pipeline.ingest --all

# Already-processed calls are skipped automatically (processed=1 flag)
# Safe to interrupt and resume — just re-run the same command

# Targeted re-runs (no API calls for ghost and trends)
python -m backend.pipeline.ingest --ghost-only       # instant
python -m backend.pipeline.ingest --trends-only
python -m backend.pipeline.ingest --compliance-only

# Force re-process everything (ignores processed=1)
python -m backend.pipeline.ingest --all --force
```

### Step 2 — Start the API (Terminal 1)

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

API: http://127.0.0.1:8000 · Interactive docs: http://127.0.0.1:8000/docs

### Step 3 — Start the dashboard (Terminal 2)

```bash
cd frontend && npm run dev
```

Dashboard: http://localhost:5173

---

## 7. API Reference

| Endpoint | Description |
|---|---|
| `GET /` | Service stats: ghost rate, processed calls |
| `GET /health` | Readiness check |
| `GET /calls/{id}` | Full call: transcript, intent, mood, resolution, evidence |
| `GET /calls/{id}/compliance` | Rule violations for one call |
| `POST /calls/{id}/compliance/evaluate` | Trigger on-demand compliance evaluation |
| `GET /calls/{id}/suggestions` | Follow-up question suggestions |
| `GET /audio/{id}` | Stream the MP3 |
| `GET /customers` | All customers with ghost rate, true resolution rate |
| `GET /customers/{name}/calls` | Full call history + frustration trajectory |
| `GET /dashboard/stats` | Top-line numbers: ghost rate, call counts |
| `GET /dashboard/attention` | Calls ranked by attention score (0–100) |
| `GET /dashboard/ghost-queue` | Ghost resolutions ranked by callback speed |
| `GET /dashboard/trends` | Intent clusters + session breakdown |
| `GET /dashboard/agents` | Per-agent ghost rates, resolution rates, handle times |
| `GET /dashboard/customer-trajectories` | Customer frustration arcs |
| `GET /dashboard/issues` | Issue frequency (`from_date` / `to_date` filters) |
| `GET /dashboard/issues/{intent}/detail` | Drill-down: dissatisfied calls + fix suggestion |
| `GET /dashboard/satisfaction` | Satisfaction metrics with date range filter |
| `GET /dashboard/performance` | Agent performance scores |
| `GET /dashboard/rude-agents` | Agent behaviour flags |
| `GET /dashboard/spam-callers` | High-frequency / self-service-eligible callers |
| `GET /dashboard/compliance` | Compliance summary across all calls |
| `GET /compliance/rules` | List all compliance rules |
| `POST /compliance/rules` | Create a custom compliance rule |

---

## 8. Project Structure

```
callradar/
├── backend/
│   ├── config.py               Settings, paths, model names — all env-driven
│   ├── db.py                   PostgreSQL connection + query helpers
│   ├── main.py                 FastAPI REST server — all dashboard endpoints
│   ├── issue_suggestions.py    Rule-based fix suggestions for Customer Perception
│   └── pipeline/
│       ├── ingest.py           Orchestrator — the only file you run directly
│       ├── transcribe.py       Dual-channel ffmpeg split → Whisper; mono fallback
│       ├── analyse.py          GPT citation-first analysis + 7-emotion sentiment
│       ├── ghost.py            Ghost resolution engine (pure SQL self-join)
│       ├── trends.py           Intent clustering (embeddings + k-means)
│       ├── compliance.py       3-stage compliance rule engine
│       ├── reranker.py         Cross-encoder reranker for compliance chunk ranking
│       └── suggestions.py      Per-call follow-up question generator
├── frontend/src/
│   ├── pages/
│   │   ├── Dashboard.jsx           Attention queue, ghost queue, trends, agents
│   │   ├── CustomerPerception.jsx  Issue frequency, satisfaction, agent flags
│   │   ├── Customers.jsx           Customer list sorted by ghost rate
│   │   ├── CustomerDetail.jsx      Mood trajectory + full call history
│   │   └── CallDetail.jsx          Playable audio + transcript + evidence
│   └── components/
│       ├── AudioPlayer.jsx         Seekable player synced to transcript
│       ├── Transcript.jsx          Speaker turns, click to seek
│       ├── MoodTimeline.jsx        Mood arc SVG
│       ├── ComplianceBadges.jsx
│       ├── EmotionRadar.jsx
│       └── AttentionScore.jsx
├── scripts/                    Dev/debug utilities (not needed to run the system)
│   ├── show_rules.py           Print all compliance rules
│   ├── check_call.py           Inspect a single call's DB record
│   ├── find_bad_calls.py       Find calls with missing analysis fields
│   ├── batch_compliance.py     Re-evaluate compliance for all calls
│   └── ...                     Other one-off inspection scripts
│   └── init_schema.py          One-time DB schema setup (safe to re-run)
├── requirements.txt
├── .env.example                Template — copy to .env and fill in credentials
└── .env                        Your credentials (not committed)
```

---

## 9. Engineering Notes & Bugs Fixed

### Compliance engine
- Rewrote 5 of the 14 rules from LLM calls to deterministic keyword/pattern checks — these ask the model to detect an *absence*, which GPT handled unreliably.
- Made rule writes atomic (DELETE + INSERT in a single transaction, only after all rules finish) so a crash mid-evaluation can't leave partial results.
- Fixed evidence-quote accuracy so the cited quote is the specific matching phrase, not the whole chunk.
- Added `asyncio.Semaphore(1)` to prevent concurrent evaluation requests from crashing the process.

### Ghost detection
- Found and fixed stale `behavioural_resolved` data (was reporting 9.5%; correct value 95% after re-running `compute_ghost_resolutions()`).
- Made ghost matching intent-aware: only same-topic callbacks count as a ghost resolution.

### Dashboard / Customer Perception
- Added a minimum score threshold and a violation-aware boost to the attention queue so it surfaces genuinely urgent calls, not just an unfiltered top-50.
- Rebuilt the spam-callers view: intents are now bucketed into 17 canonical topics; the view flags customers repeatedly calling about self-serviceable issues (balance checks, branch hours, password resets).
- Fixed undercounting of positive outcomes (previously counted only explicitly "happy" calls).
- Fixed `%%`-escaping bug in dynamically built `LIKE` queries and a blank-row bug in the Trends table caused by null trend labels.

### Other fixes
- Audio player scrubbar click now correctly resumes playback and no longer crashes on a null ref.
- Transcript component key collisions (duplicate `start_s` values) fixed by including array index in the React key.
- `init_db` connection leak fixed with a `try/finally` around the DDL loop.
- Dashboard now shows an explicit "could not reach API" state instead of failing silently.

### Known remaining issues

| Priority | Issue | Notes |
|---|---|---|
| Medium | Noisy transcripts | Background TV/audio sometimes gets transcribed by Whisper — VAD pre-processing would help |
| Medium | Agent name mismatch | Synthetic dataset artefact — an agent occasionally introduces themselves under a different name than the DB record |
| Low | CORS wildcard | `allow_origins=["*"]` is fine for a demo; restrict before production |
| Low | PostgreSQL-only | Several queries use Postgres-specific SQL (`::numeric`, `STRING_AGG`, `NULLS LAST`); no SQLite fallback |
| Low | `seed_default_rules` on every startup | Harmless (`DO NOTHING` prevents duplicates) but unnecessary I/O on every boot |

---

Questions or anything unclear in setup — reach out and we're happy to walk through it.
