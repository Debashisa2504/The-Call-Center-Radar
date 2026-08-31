import { useState } from "react";

export default function Transcript({ turns, evidence, currentTime, onSeek }) {
  const [activeEvidence, setActiveEvidence] = useState(null);

  const evidenceByTime = {};
  for (const e of (evidence || [])) {
    if (!evidenceByTime[e.timestamp_s]) evidenceByTime[e.timestamp_s] = [];
    evidenceByTime[e.timestamp_s].push(e);
  }

  const isActive = (turn) => currentTime >= turn.start_s && currentTime < turn.end_s;

  const fmt = (s) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  const JUDGMENT_LABEL = {
    intent:     "💡 Intent",
    mood_shift: "😤 Mood shift",
    resolved:   "✓ Resolution",
    key_moment: "📍 Key moment",
  };

  return (
    <div className="space-y-1 font-mono text-sm">
      {(turns || []).map((turn, idx) => {
        const ev = evidenceByTime[turn.start_s] || [];
        const active = isActive(turn);
        return (
          <div key={`${idx}-${turn.speaker}-${turn.start_s}`}>
            {ev.map((e, j) => (
              <div
                key={j}
                className="mb-1 rounded border border-blue-800 bg-blue-950/40 px-3 py-1 text-[11px] text-blue-300"
              >
                {JUDGMENT_LABEL[e.judgment_type] || e.judgment_type}
                {e.reasoning ? ` — ${e.reasoning}` : ""}
              </div>
            ))}
            <div
              onClick={() => onSeek?.({ t: turn.start_s, n: Date.now() })}
              className={`flex cursor-pointer gap-3 rounded px-2 py-1 transition-colors ${
                active ? "bg-blue-900/40 ring-1 ring-blue-700" : "hover:bg-zinc-800"
              }`}
            >
              <span className="w-10 shrink-0 text-right text-zinc-500 text-[11px] mt-0.5">
                {fmt(turn.start_s)}
              </span>
              <span className={`w-16 shrink-0 text-[11px] font-semibold uppercase tracking-wide mt-0.5 ${
                turn.speaker === "agent" ? "text-blue-400" : "text-green-400"
              }`}>
                {turn.speaker === "agent" ? "Agent" : "Customer"}
              </span>
              <span className="text-zinc-200 text-xs leading-relaxed">{turn.text}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
