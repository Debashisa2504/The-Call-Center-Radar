"""
backend/pipeline/transcribe.py
================================
Step 1 — Dual-channel transcription with pause-gap boundary chunking.

Improvements from CortexV
--------------------------
1.  Pause-gap boundary chunking
    Instead of fixed 400-word windows, chunks are flushed at natural
    conversation boundaries: a silence gap >= CHUNK_PAUSE_GAP_SEC (3s)
    combined with soft minimums on utterance count and span duration.
    This keeps semantically coherent exchange groups together.

2.  Long-monologue sentence-aware splitting
    A single agent turn exceeding CHUNK_MAX_WORDS is split on sentence
    boundaries (_SENT_BOUNDARY regex) with CHUNK_OVERLAP_WORDS carry-over
    and proportional timestamp interpolation — never mid-sentence.

3.  Negative-gap merge guard
    Same-speaker segments are only merged when the gap is >= 0 seconds.
    Overlapping cues (talk-over artefacts from the phone system) are kept
    as separate turns, never concatenated.

4.  Free-layer contextual text enrichment
    Before returning chunks, each chunk's embedding text is enriched with
    call metadata (date, agent, customer) so the embedding captures who/
    when/what — not just isolated utterance text. Based on Anthropic's
    Contextual Retrieval research: reduces retrieval failures 35-49%.

Architecture
------------
transcribe_call()
  → _split_channels()         ffmpeg: dual-channel MP3 → two mono WAVs
  → _transcribe_channel()     OpenAI Whisper API per channel
  → _merge_turns()            interleave by timestamp, negative-gap guard
  → chunk_turns()             pause-gap boundary chunker
  → _enrich_chunks()          free-layer contextual text enrichment
  → returns (turns, chunks)
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import (
    WHISPER_MODEL, make_openai_client,
    CHUNK_MAX_UTTERANCES, CHUNK_MAX_SPAN_SEC, CHUNK_MAX_WORDS,
    CHUNK_SOFT_MIN_UTTERANCES, CHUNK_SOFT_MIN_SPAN_SEC, CHUNK_PAUSE_GAP_SEC,
    CHUNK_OVERLAP_WORDS, CHUNK_MERGE_GAP_SEC, CONTEXT_ENRICHMENT,
)

client = make_openai_client()

# Sentence boundary: end of a sentence followed by a capital or quote.
_SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"])")


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class Turn:
    """A single speaker utterance."""
    speaker: str
    text:    str
    start_s: float
    end_s:   float


@dataclass
class CallChunk:
    """
    A pause-gap-bounded multi-turn chunk ready for embedding and compliance.

    chunk_index    : sequential 0-based index within the call
    turns          : ordered list of Turn objects
    contextual_text: enriched text fed to the embedder (metadata + turns)
    """
    chunk_index:     int
    turns:           List[Turn] = field(default_factory=list)
    contextual_text: str        = ""

    @property
    def start_s(self) -> float:
        return self.turns[0].start_s if self.turns else 0.0

    @property
    def end_s(self) -> float:
        return self.turns[-1].end_s if self.turns else 0.0

    @property
    def text(self) -> str:
        return " ".join(t.text for t in self.turns if t.text)

    @property
    def speaker(self) -> str:
        return self.turns[0].speaker if self.turns else ""

    @property
    def word_count(self) -> int:
        return len(self.text.split())


# ── Channel splitting & Whisper transcription ──────────────────────────────────

def _ffmpeg_exe() -> str:
    """Return path to ffmpeg binary — bundled via imageio-ffmpeg if available."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def _split_channels(mp3_path: Path) -> Tuple[Path, Path]:
    """
    Split dual-channel MP3 into two mono 16kHz WAVs.
    Left channel (0) = agent.
    Right channel (1) = customer.
    Returns (agent_wav, customer_wav) paths in a temp directory.
    """
    import subprocess
    ffmpeg = _ffmpeg_exe()
    tmp_dir = Path(tempfile.mkdtemp())
    agent_wav    = tmp_dir / "agent.wav"
    customer_wav = tmp_dir / "customer.wav"
    subprocess.run(
        [ffmpeg, "-y", "-i", str(mp3_path),
         "-filter_complex", "[0:a]pan=mono|c0=c0[left]", "-map", "[left]",
         "-ar", "16000", "-ac", "1", str(agent_wav), "-loglevel", "error"],
        check=False,
    )
    subprocess.run(
        [ffmpeg, "-y", "-i", str(mp3_path),
         "-filter_complex", "[0:a]pan=mono|c0=c1[right]", "-map", "[right]",
         "-ar", "16000", "-ac", "1", str(customer_wav), "-loglevel", "error"],
        check=False,
    )
    return agent_wav, customer_wav


def _channel_rms(wav_path: Path) -> float:
    """Return RMS energy (0–1) of a mono WAV. Returns 0 on any error."""
    try:
        import wave, struct, math
        with wave.open(str(wav_path), "rb") as w:
            raw = w.readframes(w.getnframes())
        if not raw:
            return 0.0
        samples = struct.unpack(f"{len(raw) // 2}h", raw)
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0
        return rms
    except Exception:
        return 0.0


def _transcribe_mono_with_alternation(wav_path: Path) -> Tuple[List[Dict], List[Dict]]:
    """
    Fallback for single-channel (mono) recordings where both channels
    contain the same mixed audio.

    Transcribes once, then assigns speaker labels by alternating on pause
    boundaries (gap > 1 s = speaker change). Agent always starts.
    Returns (agent_segs, customer_segs).
    """
    all_segs = _transcribe_channel(wav_path, "agent")
    agent_segs: List[Dict] = []
    customer_segs: List[Dict] = []
    current_speaker = "agent"
    for i, seg in enumerate(all_segs):
        if i > 0:
            gap = seg["start_s"] - all_segs[i - 1]["end_s"]
            if gap > 1.0:
                current_speaker = "customer" if current_speaker == "agent" else "agent"
        entry = dict(seg, speaker=current_speaker)
        if current_speaker == "agent":
            agent_segs.append(entry)
        else:
            customer_segs.append(entry)
    return agent_segs, customer_segs


def _transcribe_channel(wav_path: Path, speaker: str) -> List[Dict[str, Any]]:
    """
    Transcribe one mono WAV via OpenAI Whisper API.
    Returns list of {speaker, start_s, end_s, text} dicts.
    Retries up to 5 times on rate limit (429) with exponential backoff.
    """
    import time
    from openai import RateLimitError

    max_retries = 5
    for attempt in range(max_retries):
        try:
            with open(wav_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    model=WHISPER_MODEL,
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
            break  # success
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            wait = 60 * (2 ** attempt)  # 60s, 120s, 240s, 480s
            print(f"    [RATE LIMIT] Whisper {speaker} — waiting {wait}s (attempt {attempt+1}/{max_retries})")
            time.sleep(wait)
    segments = []
    for seg in (result.segments or []):
        text = seg.text.strip()
        if not text:
            continue
        segments.append({
            "speaker": speaker,
            "start_s": round(float(seg.start), 3),
            "end_s":   round(float(seg.end),   3),
            "text":    text,
        })
    return segments


def _merge_turns(
    agent_segs: List[Dict], customer_segs: List[Dict]
) -> List[Dict]:
    """
    Interleave agent and customer segments by start_s.

    Negative-gap guard (CortexV A.3 fix):
    When curr.start_s < prev.end_s the cues overlap in time — phone systems
    sometimes emit these at talk-over boundaries. Merging would duplicate
    text, so overlapping cues from the same speaker are kept separate.
    Only consecutive same-speaker segments with gap <= CHUNK_MERGE_GAP_SEC
    AND gap >= 0 are merged.
    """
    all_segs = sorted(agent_segs + customer_segs, key=lambda s: s["start_s"])
    if not all_segs:
        return []

    merged = [all_segs[0].copy()]
    for seg in all_segs[1:]:
        prev = merged[-1]
        gap  = seg["start_s"] - prev["end_s"]
        if (seg["speaker"] == prev["speaker"]
                and 0.0 <= gap <= CHUNK_MERGE_GAP_SEC):
            prev["text"]  += " " + seg["text"]
            prev["end_s"]  = seg["end_s"]
        else:
            merged.append(seg.copy())
    return merged


# ── Pause-gap boundary chunker (CortexV improvement) ──────────────────────────

def _hard_cap_exceeded(chunk: CallChunk, words: int) -> bool:
    if len(chunk.turns) >= CHUNK_MAX_UTTERANCES:
        return True
    if (chunk.end_s - chunk.start_s) >= CHUNK_MAX_SPAN_SEC:
        return True
    return words >= CHUNK_MAX_WORDS


def _pause_break(chunk: CallChunk, gap_s: float) -> bool:
    if gap_s < CHUNK_PAUSE_GAP_SEC:
        return False
    if len(chunk.turns) < CHUNK_SOFT_MIN_UTTERANCES:
        return False
    return (chunk.end_s - chunk.start_s) >= CHUNK_SOFT_MIN_SPAN_SEC


def _split_long_turn(seg: Dict) -> List[Turn]:
    """
    Split a single oversized turn (> CHUNK_MAX_WORDS) into sentence-aware
    sub-turns with CHUNK_OVERLAP_WORDS carry-over and proportional timestamp
    interpolation.  Falls back to word-count splitting when no sentence
    boundaries are detected (CortexV A.7 fix).
    """
    text         = seg["text"]
    total_words  = len(text.split())
    duration_s   = seg["end_s"] - seg["start_s"]
    sentences    = _SENT_BOUNDARY.split(text)
    if len(sentences) == 1:
        words  = text.split()
        sentences = [
            " ".join(words[i: i + CHUNK_MAX_WORDS])
            for i in range(0, len(words), CHUNK_MAX_WORDS)
        ]

    def interp_s(word_pos: int) -> float:
        if total_words == 0 or duration_s == 0:
            return seg["start_s"]
        return seg["start_s"] + duration_s * word_pos / total_words

    sub_turns:     List[Turn] = []
    buf_sentences: List[str]  = []
    buf_words:     int        = 0
    words_consumed:int        = 0

    def emit(final: bool) -> Tuple[List[str], int]:
        nonlocal words_consumed
        chunk_text  = " ".join(buf_sentences)
        start_word  = max(0, words_consumed - buf_words)
        start_s     = interp_s(start_word)
        end_s       = seg["end_s"] if final else interp_s(words_consumed)
        if end_s <= start_s:
            end_s = start_s + 0.01
        sub_turns.append(Turn(
            speaker=seg["speaker"],
            text=chunk_text,
            start_s=round(start_s, 3),
            end_s=round(end_s, 3),
        ))
        if final:
            return [], 0
        tail = chunk_text.split()[-CHUNK_OVERLAP_WORDS:]
        return [" ".join(tail)], len(tail)

    for sent in sentences:
        sw = len(sent.split())
        if buf_words + sw > CHUNK_MAX_WORDS and buf_words >= 20:
            buf_sentences, buf_words = emit(final=False)
        buf_sentences.append(sent)
        buf_words      += sw
        words_consumed += sw

    if buf_sentences:
        emit(final=True)

    return sub_turns


def chunk_turns(raw_turns: List[Dict]) -> List[CallChunk]:
    """
    Pack merged turns into CallChunks using three boundary triggers:

    1. Hard cap   — emit when utterance count, span, or word count exceeds max.
    2. Pause gap  — emit when silence to the next turn >= CHUNK_PAUSE_GAP_SEC
                    and soft minimums (utterances + span) are met.
    3. End of stream — always flush remaining buffer.

    Long-monologue fallback: a single turn exceeding CHUNK_MAX_WORDS is split
    sentence-aware with overlap carry-over, each sub-turn becomes its own chunk.
    """
    chunks:        List[CallChunk] = []
    current:       CallChunk       = CallChunk(chunk_index=0)
    current_words: int             = 0

    def flush():
        nonlocal current, current_words
        if current.turns:
            chunks.append(current)
        current       = CallChunk(chunk_index=len(chunks))
        current_words = 0

    for i, seg in enumerate(raw_turns):
        if not seg.get("text"):
            continue
        seg_words = len(seg["text"].split())

        # Long-monologue fallback
        if seg_words > CHUNK_MAX_WORDS:
            flush()
            for sub in _split_long_turn(seg):
                c = CallChunk(chunk_index=len(chunks), turns=[sub])
                chunks.append(c)
            current       = CallChunk(chunk_index=len(chunks))
            current_words = 0
            continue

        current.turns.append(Turn(
            speaker=seg["speaker"],
            text=seg["text"],
            start_s=seg["start_s"],
            end_s=seg["end_s"],
        ))
        current_words += seg_words

        # Trigger 1: hard cap
        if _hard_cap_exceeded(current, current_words):
            flush()
            continue

        # Trigger 2: pause break (look ahead)
        if i + 1 < len(raw_turns):
            gap_s = raw_turns[i + 1]["start_s"] - seg["end_s"]
            if _pause_break(current, gap_s):
                flush()

    # Trigger 3: end of stream
    flush()

    # Reindex sequentially
    for j, c in enumerate(chunks):
        c.chunk_index = j
    return chunks


# ── Free-layer contextual text enrichment (CortexV improvement) ───────────────

def _build_contextual_text(
    chunk:         CallChunk,
    call_date:     str,
    agent_name:    str,
    customer_name: str,
) -> str:
    """
    Prepends call metadata to the chunk text before embedding.

    Based on Anthropic's Contextual Retrieval research: prepending a short
    context description reduces retrieval failures by 35-49% compared to
    embedding raw chunk text alone.  Zero API cost.

    Format:
      "Bank call: 2020-06-01. Agent: Robert. Customer: James Williams.
       Speaker Agent: <turn text>"
    """
    header = (
        f"Bank call: {call_date}. "
        f"Agent: {agent_name}. "
        f"Customer: {customer_name}."
    )
    # Format turns as "Speaker Role: text"
    lines = []
    for t in chunk.turns:
        role = "Agent" if t.speaker == "agent" else "Customer"
        if t.text:
            lines.append(f"Speaker {role}: {t.text}")
    body = " ".join(lines)
    return f"{header} {body}"


def _enrich_chunks(
    chunks:        List[CallChunk],
    call_date:     str,
    agent_name:    str,
    customer_name: str,
) -> None:
    """
    Mutates each chunk in-place: sets contextual_text to the enriched
    string that will be passed to the embedder.
    """
    if not CONTEXT_ENRICHMENT:
        for c in chunks:
            c.contextual_text = c.text
        return

    for c in chunks:
        c.contextual_text = _build_contextual_text(
            c, call_date, agent_name, customer_name
        )


# ── Public entry point ─────────────────────────────────────────────────────────

def transcribe_call(
    mp3_path:      Path,
    agent_name:    str = "Agent",
    customer_name: str = "Customer",
    call_date:     str = "",
) -> Tuple[List[Dict[str, Any]], List[CallChunk]]:
    """
    Full transcription + chunking pipeline for one call.

    Returns:
        turns  : flat list of {speaker, start_s, end_s, text} dicts
                 (stored in the turns table for the transcript view)
        chunks : list of CallChunk objects
                 (stored in the chunks table for search + compliance)
    """
    agent_wav, customer_wav = _split_channels(mp3_path)
    try:
        # If the customer channel is near-silent the recording is mono
        # (both channels carry the same mixed audio). Transcribing twice
        # produces garbled, duplicated, out-of-order turns. Instead,
        # transcribe once and assign speakers by alternating on pauses.
        customer_rms = _channel_rms(customer_wav)
        if customer_rms < 0.01:
            print(f"    [MONO] customer channel RMS={customer_rms:.4f} — using alternation mode")
            agent_segs, customer_segs = _transcribe_mono_with_alternation(agent_wav)
        else:
            agent_segs    = _transcribe_channel(agent_wav,    "agent")
            customer_segs = _transcribe_channel(customer_wav, "customer")
        turns = _merge_turns(agent_segs, customer_segs)
    finally:
        agent_wav.unlink(missing_ok=True)
        customer_wav.unlink(missing_ok=True)
        agent_wav.parent.rmdir()

    chunks = chunk_turns(turns)
    _enrich_chunks(chunks, call_date, agent_name, customer_name)
    return turns, chunks
