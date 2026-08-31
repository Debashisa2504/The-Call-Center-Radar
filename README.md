# Call Radar — Ghost Resolution Intelligence

> "Everyone else tells you what happened on the call. We tell you what happened after."

**Team: Ghost Hunters** — Debashisa Behera · Aakansha Sharma  
Call-Centre Analytics Hackathon 2026

## The core insight

**Ghost Resolutions** — the agent said the issue was resolved, but the customer called back within 30 minutes. Every other call-centre tool misses this because it analyses calls in isolation. Call Radar connects them.

35.2% of calls marked resolved in our dataset are Ghost Resolutions.

## What makes this different

| Signal | Generic tool | Call Radar |
|---|---|---|
| Transcript | ✓ | ✓ |
| Intent, mood, resolution | ✓ | ✓ |
| **Ghost resolution detection** | ✗ | ✓ cross-call analysis |
| **Behavioural resolution** (not claimed) | ✗ | ✓ customer behaviour = truth |
| **Customer frustration trajectory** | ✗ | ✓ |
| **Agent ghost rate leaderboard** | ✗ | ✓ |
| **Per-channel speaker attribution** | ✗ | ✓ no diarization needed |
| **Evidence citations** (timestamp + quote) | ✗ | ✓ every judgment cited |
| **Compliance rule engine** | ✗ | ✓ 3-stage: pre-filter → judge → verify |

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- ffmpeg — `winget install ffmpeg` (Windows) or `brew install ffmpeg` (Mac)
- Azure OpenAI account with deployments: `gpt-4o`, `text-embedding-3-large`, `whisper`
- PostgreSQL — **required**. `DATABASE_URL` must be set; the app raises a clear error on startup if it's missing.
---

## Setup (run once)

### 1. Clone and enter the repo

```bash
git clone <repo-url>
cd callradar
```

### 2. Place call recordings

Unzip `callradar-data.zip` inside the project so the layout is:

```
callradar/
├── callradar-data/
│   ├── audio/       ← .mp3 files (stereo: left=agent, right=customer)
│   └── metadata/    ← .json files (one per call)
```

### 3. Python environment

**Windows (PowerShell):**
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Mac/Linux:**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Environment variables

```bash
cp .env.example .env
```

Fill in your credentials in `.env`:

```
# OpenAI / Azure OpenAI
OPENAI_API_KEY=<your-key>

# PostgreSQL — required, see Prerequisites above
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Model overrides (must match your Azure OpenAI deployment names)
ANALYSIS_MODEL=gpt-4o
EMBED_MODEL=text-embedding-3-large
WHISPER_MODEL=whisper

# Ghost detection window in minutes (default 30)
GHOST_WINDOW_MIN=30
```

### 5. Frontend packages

```bash
cd frontend && npm install && cd ..
```

---

## Running the system

### Step 1 — Ingest calls (turns recordings into transcripts and analysis)

This is the step that processes the raw MP3s. It splits each stereo recording into two channels, transcribes both with Whisper, runs GPT-4o analysis, then detects ghost resolutions with a pure SQL self-join.

```bash
# Test with a small batch first (~2 min per call)
python -m backend.pipeline.ingest --all --limit 10

# Full ingest — processes everything in callradar-data/
python -m backend.pipeline.ingest --all

# Re-run ghost detection only (no API calls, instant)
python -m backend.pipeline.ingest --ghost-only

# Re-run intent clustering only
python -m backend.pipeline.ingest --trends-only
```

### Step 2 — Start the API (Terminal 1)

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
# API at http://127.0.0.1:8000
# Interactive docs at http://127.0.0.1:8000/docs
```

### Step 3 — Start the dashboard (Terminal 2)

```bash
cd frontend && npm run dev
# Dashboard at http://localhost:5173
```

---

## API reference

| Endpoint | Description |
|---|---|
| `GET /` | Service stats: ghost rate, processed calls |
| `GET /health` | Readiness check |
| `GET /calls/{id}` | Full call: transcript, intent, mood, resolution, evidence |
| `GET /audio/{id}` | Stream the MP3 |
| `GET /customers` | All customers with ghost rate, true resolution rate |
| `GET /customers/{name}/calls` | Full call history + trajectory |
| `GET /dashboard/attention` | Calls ranked by attention score (0–100) |
| `GET /dashboard/ghost-queue` | Ghost resolutions ranked by callback speed |
| `GET /dashboard/trends` | Intent clusters + session breakdown |
| `GET /dashboard/agents` | Per-agent ghost rates, resolution rates, handle times |
| `GET /dashboard/customer-trajectories` | Customer frustration arcs |
| `GET /dashboard/stats` | Top-line numbers |
| `GET /dashboard/issues` | Issue frequency with optional date range (`from_date`, `to_date`) |
| `GET /dashboard/satisfaction` | Customer satisfaction metrics with date range filter |
| `GET /dashboard/performance` | Agent performance scores |
| `GET /dashboard/rude-agents` | Agent behaviour flags |
| `GET /dashboard/spam-callers` | High-frequency / spam caller list |

---

## The Ghost Resolution concept

A **Ghost Resolution** occurs when:
1. The transcript analysis says the issue was resolved (`transcript_resolved = true`)
2. The same customer calls back within 30 minutes (`ghost_resolved = true`)

This is stronger evidence of failure than any sentiment analysis. The customer's behaviour is the ground truth.

**Behavioural resolution** (`behavioural_resolved = true`) = transcript resolved AND no callback within 30 min = the issue was actually fixed.

Ghost detection runs as a pure SQL self-join — zero API cost, re-runnable at any time.

---

## Project structure

```
callradar/
├── backend/
│   ├── config.py           Settings, paths, model names
│   ├── db.py               PostgreSQL connection + query helpers
│   ├── main.py             FastAPI REST server
│   └── pipeline/
│       ├── ingest.py       Orchestrator — run this to process calls
│       ├── transcribe.py   Dual-channel ffmpeg split → Whisper API
│       ├── analyse.py      GPT-4o citation-first analysis + 7-emotion sentiment
│       ├── ghost.py        Ghost resolution engine (pure SQL self-join)
│       ├── trends.py       Intent clustering (embeddings + k-means)
│       ├── compliance.py   Compliance rule engine (3-stage LLM judge)
│       ├── reranker.py     Cross-encoder reranker for compliance chunk ranking
│       └── suggestions.py  Per-call follow-up question generator
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.jsx          Attention queue, ghost queue, trends, agents
│       │   ├── CustomerPerception.jsx Issue frequency, satisfaction, agent flags
│       │   ├── Customers.jsx          Customer list sorted by ghost rate
│       │   ├── CustomerDetail.jsx     Mood trajectory + full call history
│       │   └── CallDetail.jsx         Playable audio + transcript + evidence
│       └── components/
│           ├── AudioPlayer.jsx        Seekable player synced to transcript
│           ├── Transcript.jsx         Speaker turns, click to seek
│           ├── MoodTimeline.jsx       Mood arc SVG
│           └── ...
├── requirements.txt
├── .env.example
└── README.md
```

## Database

PostgreSQL. Seven tables:

| Table | Purpose |
|---|---|
| `calls` | One row per call — all analysis, ghost resolution, sentiment, timing fields |
| `turns` | Transcript speaker turns: speaker, start_s, end_s, text |
| `chunks` | Embedded transcript chunks used by compliance pre-filter (vector(3072)) |
| `evidence` | Citation triplets per judgment: `(judgment_type, timestamp_s, quote, reasoning)` |
| `trends` | Intent cluster labels from k-means |
| `compliance_rules` | Configurable rules: name, description, severity, enabled |
| `rule_violations` | Per-call rule results: `(call_id, rule_id, had_violation, severity, evidence_json)` |

Data is only written during ingestion. All API calls are read-only.
