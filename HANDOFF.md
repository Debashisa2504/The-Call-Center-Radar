# CallRadar — Handoff Document

## Project Location
`C:\Users\Debashisa Behera\Downloads\files6_extracted\callradar-v2\callradar`

## What Is CallRadar
A call-centre intelligence platform built for Harper Valley National Bank that:
- Transcribes calls (Whisper), analyses sentiment / mood / emotion (GPT-4o)
- Detects **Ghost Resolution** (agent marks resolved but customer calls back within 30 min — SQL self-join)
- Runs **compliance evaluation** against 14 rules using GPT-4o + deterministic keyword checks
- Frontend: React + Vite + Tailwind · Backend: FastAPI + PostgreSQL + pgvector + Azure OpenAI

---

## Azure OpenAI Models (IMPORTANT — do not change)
| Env var | Deployed model |
|---|---|
| `ANALYSIS_MODEL` | `gpt-4o` (GlobalStandard) |
| `EMBED_MODEL` | `text-embedding-3-large` (GlobalStandard) |
| `WHISPER_MODEL` | `whisper` (Standard) |

---

## Start Commands
```bash
# Backend (from callradar/ directory)
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Frontend (from callradar/ directory)
cd frontend && npm run dev
```

---

## Key Files
| File | Role |
|---|---|
| `backend/pipeline/compliance.py` | Compliance engine — pre-filter, GPT evaluator, 5 deterministic checks |
| `backend/main.py` | FastAPI routes — all API endpoints |
| `backend/db.py` | PGConn wrapper — use `conn.execute()` NOT `conn.cursor()` |
| `frontend/src/pages/CallDetail.jsx` | Call detail page + compliance trigger + polling |
| `frontend/src/pages/Dashboard.jsx` | Main dashboard — Ghost / Attention / Trends / Agents tabs |
| `frontend/src/pages/CustomerPerception.jsx` | Perception page — Issues / Satisfaction / Performance / Flags |
| `frontend/src/components/ComplianceBadges.jsx` | Compliance badge display |
| `frontend/src/components/Transcript.jsx` | Clickable transcript with evidence markers |
| `frontend/src/components/AudioPlayer.jsx` | MP3 player with scrubbar seek |
| `frontend/src/api.js` | API client |

---

## DB Notes
- PGConn wrapper: `conn.execute(sql, params)` returns cursor-like object — NO `.cursor()` method
- `?` placeholders are auto-converted to `%s` by PGConn wrapper; use `?` everywhere
- `had_violation` and `enabled` columns are integer (1/0), not boolean — Python path converts them
- LIKE patterns need `%%` not `%` in f-strings when building SQL dynamically
- `with db() as conn:` auto-commits on exit and rolls back on exception

---

## Compliance Engine Architecture

### Rule Evaluation Flow
```
evaluate_call_compliance(call_id)
  ├─ Load enabled rules from compliance_rules table
  ├─ Load all chunks for the call (text + embedding vectors)
  ├─ For each rule:
  │   ├─ Deterministic checks (RULE_003/011/012/013/014) → queue result
  │   └─ LLM path (all other rules):
  │       ├─ Pre-filter: cosine similarity + keyword match to find relevant chunks
  │       ├─ Build prompt window from top-k chunks
  │       ├─ Call GPT-4o evaluator
  │       ├─ Shape + verify violations
  │       └─ Queue result
  └─ Atomic flush: DELETE old records + INSERT all 14 results in one transaction
```

### Deterministic Rules (bypass GPT — reliable)
| Rule | Check |
|---|---|
| RULE_003 | Transfer keywords present but no fraud disclosure words → flag |
| RULE_011 | No closing confirmation question ("is there anything else?") → flag |
| RULE_012 | Unresolved signals present but no escalation offer → flag |
| RULE_013 | Frustration signals present but no acknowledgement → flag |
| RULE_014 | Agent re-asked info customer already provided (pattern matching) → flag |

### Atomic Write Design
- **Before loop**: no DELETE (old records remain visible during evaluation)
- **After loop completes**: single transaction — DELETE old records + INSERT all 14 fresh results
- **If loop raises exception**: old records remain (graceful degradation, user can re-evaluate)
- **Frontend polling**: detects fresh results when count ≥ ruleCount OR rule IDs changed from pre-eval snapshot

---

## Demo Cases

### Negative Case (Violations Found)
**Call:** Jennifer Garcia → Agent Michael  
**Call ID:** `1dcef09fb6374319`  
**URL:** `http://localhost:5173/calls/1dcef09fb6374319`  
Shows 3 violations: RULE_003 (fraud disclosure), RULE_012 (no escalation), RULE_014 (re-asked account type)

### Positive Case (All Rules Pass)
**Call:** Michael Williams → Agent James  
All 14 rules pass — agent did everything correctly.

### Clean Evaluation Test
**Call:** Mary Johnson → Agent Mary  
**Call ID:** `51aec7fcd6894d76`  
Simple balance enquiry — all 14 rules correctly pass.

---

## Bugs Fixed This Project

### Session 1 Fixes
| Fix | File | Description |
|---|---|---|
| Compliance polling | `CallDetail.jsx` | Changed single 5s timeout → poll-every-4s-for-90s loop |
| ComplianceBadges | `ComplianceBadges.jsx` | Added green "✓ All X rules passed" state |
| Dynamic rule count | `CallDetail.jsx` | Button shows live rule count from API |
| Omission rule pre-filter | `compliance.py` | Added fallback keyword retry with call-ending phrases |
| GPT evaluator prompt | `compliance.py` | Added explicit instruction about absence-based rules |
| RULE_003 deterministic | `compliance.py` | Keyword check for fraud disclosure before transfer |
| Rules RULE_011–014 added | DB | Four new compliance rules seeded |

### Session 2 Fixes
| Fix | File | Description |
|---|---|---|
| RULE_011/012/013 deterministic | `compliance.py` | Keyword-based checks replacing GPT for these omission rules |
| RULE_014 deterministic | `compliance.py` | Pattern matching for repeated information requests |
| Evidence quote accuracy | `compliance.py` | `_extract_phrase()` finds specific phrase within chunk |
| Semaphore rate limiting | `main.py` | `asyncio.Semaphore(1)` prevents concurrent eval crashes |
| Batch evaluate script | `batch_compliance.py` | Evaluate all 1400 calls in ~30s, deterministic only |
| Blank Perception row | `Dashboard.jsx` | Filter null trend_labels |
| Clear-before-evaluate | `compliance.py` | DELETE old records so polling waits for fresh results |

### Session 5 Fixes (Latest) — Dashboard & Customer Perception
| Fix | File | Description |
|---|---|---|
| `behavioural_resolved` stale data | `ghost.py` | Re-ran `compute_ghost_resolutions()` — was 9.5% (stale), now 95% (correct) |
| Ghost resolution intent-aware | `ghost.py` | Same-topic callbacks only flagged as ghost; different-topic callbacks are new calls. Added `_same_intent()` helper |
| Attention queue threshold | `main.py` | Added `min_score=75` filter; ghost/violation boost in effective sort score; was returning all top-50 regardless of urgency |
| Attention queue violation boost | `main.py` | Left JOIN `rule_violations` — calls with violations get up to +30 effective score |
| Spam callers — topic bucketing | `main.py` | Full-sentence intents bucketed into 17 canonical topics via CASE/LIKE; `COUNT(DISTINCT topic)` gives real repeat rate |
| Spam callers — self-service detection | `main.py` | Flags customers repeatedly calling about balance/branch hours/password reset etc. that could be resolved digitally |
| Spam callers — `%%` escaping | `main.py` | LIKE patterns in f-string query needed `%%` not `%` for psycopg2 |
| +VE OUTCOMES always 0-10% | `main.py` | Was counting only `satisfied/happy/engaged` (40/826 calls); now counts NOT IN `frustrated/concerned/angry/anxious` — neutral = positive outcome |
| Spam callers — no intent always 0 | `main.py` | Intent is full sentence, never NULL; removed no_intent column, replaced with self_service_calls + repeat_rate_pct |
| Frontend spam table columns | `CustomerPerception.jsx` | Renamed "Short calls"→"Self-service calls", "No intent"→"Repeat rate", "Spam score"→"Trivial score"; updated description |
| Run ghost detection after ingest | `ghost.py` | Must call `compute_ghost_resolutions()` after each batch ingest or behavioural_resolved drifts |

### Session 3 Fixes
| Fix | File | Description |
|---|---|---|
| Atomic write (14-rule race) | `compliance.py` | DELETE + INSERT at end of loop, not mid-evaluation |
| Poll detects fresh results | `CallDetail.jsx` | Compares rule IDs to pre-eval snapshot, not just length > 0 |
| `violations_found` type fix | `compliance.py` | Always appends dict, not string |
| `AudioPlayer` scrubbar | `AudioPlayer.jsx` | Scrubbar click now also calls `.play()` + null guard |
| `Transcript` key collision | `Transcript.jsx` | Key includes array index to prevent duplicate start_s collisions |
| `ghost_queue` NULL ordering | `main.py` | `ORDER BY ghost_gap_min ASC NULLS LAST` |
| `get_call_violations` order | `compliance.py` | `ORDER BY rule_id ASC` for stable deterministic ordering |
| `init_db` connection leak | `db.py` | Wrapped DDL loop in try/finally to guarantee conn.close() |
| Dashboard error state | `Dashboard.jsx` | Shows "Could not reach API" message on total failure |

---

## Helper Scripts (project root)
| Script | Purpose |
|---|---|
| `batch_compliance.py` | Evaluate all 1400 calls deterministically — ~30s, no GPT |
| `show_rules.py` | List all compliance rules |
| `check_rules.py` | Show rule IDs with enabled status |
| `find_bad_calls.py` | Find unresolved/dissatisfied calls |
| `find_best_violation.py` | Find calls likely to violate rules |
| `show_transcript.py` | Print transcript chunks for a call_id |
| `check_any_violations.py` | Show all flagged violations in DB |
| `check_call.py` | Show rule results for a specific call_id |
| `add_rules.py` | Add RULE_011/012/013 (run once) |
| `add_rule014.py` | Add RULE_014 (run once) |

---

## Known Remaining Issues
| Priority | Issue | Notes |
|---|---|---|
| Medium | Noisy transcripts (Whisper) | Background TV audio transcribed — VAD pre-processing needed |
| Medium | Agent name mismatch | Synthetic data artefact — agent says "this is Mary" but DB says Robert |
| Low | CORS wildcard | `allow_origins=["*"]` fine for demo, restrict in production |
| Low | SQLite fallback | PostgreSQL-specific SQL (`::numeric`, `STRING_AGG`, `NULLS LAST`) breaks SQLite fallback — project is PostgreSQL-only |
| Low | `seed_default_rules` on every startup | Runs 10 INSERTs on every server start (DO NOTHING prevents duplicates, just inefficient) |
