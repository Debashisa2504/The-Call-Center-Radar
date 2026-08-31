import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import MoodBadge from "../components/MoodBadge.jsx";
import ResolutionBadge from "../components/ResolutionBadge.jsx";
import AttentionScore from "../components/AttentionScore.jsx";
import Pagination from "../components/Pagination.jsx";

const PAGE_SIZE = 10;

export default function CustomerDetail() {
  const { name } = useParams();
  const nav = useNavigate();
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);
  const [callPage, setCallPage] = useState(1);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.customerCalls(name)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => { setError("Failed to load customer data."); setLoading(false); });
  }, [name]);

  if (loading) return <p className="animate-pulse font-mono text-sm text-zinc-500 p-8">Loading…</p>;
  if (error)   return <p className="text-red-400 p-8">{error}</p>;
  if (!data)   return <p className="text-red-400 p-8">Customer not found.</p>;

  const calls = data?.calls ?? [];

  if (calls.length === 0) return (
    <div className="space-y-4">
      <button onClick={() => nav("/customers")} className="font-mono text-xs text-zinc-500 hover:text-zinc-300">
        ← Customers
      </button>
      <h1 className="text-xl font-semibold">{decodeURIComponent(name)}</h1>
      <p className="text-zinc-500">No calls found for this customer.</p>
    </div>
  );

  const ghost_count = calls.filter(c => c.ghost_resolved).length;
  const true_res    = calls.filter(c => c.behavioural_resolved).length;

  const MOOD_SCORE = { satisfied: 5, calm: 4, confused: 3, frustrated: 2, angry: 1 };
  const moodArc = calls.map(c => MOOD_SCORE[c.mood_start] ?? 3);
  const svgW = 500, svgH = 60;

  const pts = calls.length === 1
    ? null
    : moodArc.map((y, i) => {
        const x = (i / Math.max(calls.length - 1, 1)) * (svgW - 40) + 20;
        const yCoord = svgH - ((y - 1) / 4) * (svgH - 10) - 5;
        return `${x},${yCoord}`;
      }).join(" ");

  return (
    <div className="space-y-5">
      <button onClick={() => nav("/customers")} className="font-mono text-xs text-zinc-500 hover:text-zinc-300">
        ← Customers
      </button>
      <div className="flex items-start justify-between">
        <h1 className="text-xl font-semibold">{decodeURIComponent(name)}</h1>
        <span className={`font-mono text-sm font-semibold ${
          data.mood_trajectory === "deteriorating" ? "text-red-400" :
          data.mood_trajectory === "improving"     ? "text-green-400" : "text-zinc-400"
        }`}>
          Trajectory: {data.mood_trajectory ?? "unknown"}
        </span>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-center">
          <p className="font-mono text-2xl font-semibold">{data.total_calls}</p>
          <p className="text-xs text-zinc-500">Total calls</p>
        </div>
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-center">
          <p className="font-mono text-2xl font-semibold text-red-400">{ghost_count}</p>
          <p className="text-xs text-zinc-500">Ghost resolutions</p>
        </div>
        <div className="rounded-lg border border-green-800 bg-green-950/30 p-3 text-center">
          <p className="font-mono text-2xl font-semibold text-green-400">{true_res}</p>
          <p className="text-xs text-zinc-500">Truly resolved</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-center">
          <p className="font-mono text-2xl font-semibold">{data.ghost_rate_pct}%</p>
          <p className="text-xs text-zinc-500">Ghost rate</p>
        </div>
      </div>

      {/* Mood arc */}
      <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-4">
        <p className="mb-2 font-mono text-xs uppercase tracking-wide text-zinc-500">
          Mood trajectory across {calls.length} call{calls.length !== 1 ? "s" : ""}
        </p>
        <svg width="100%" viewBox={`0 0 ${svgW} ${svgH}`}>
          {[{ l: "satisfied", y: 5 }, { l: "calm", y: 18 }, { l: "confused", y: 33 }, { l: "frustrated", y: 47 }, { l: "angry", y: 57 }].map(m => (
            <line key={m.l} x1="0" y1={m.y} x2={svgW} y2={m.y} stroke="#27272a" strokeWidth="0.5" />
          ))}
          {pts
            ? <polyline points={pts} fill="none" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round" />
            : null
          }
          {moodArc.map((y, i) => {
            const x = (i / Math.max(calls.length - 1, 1)) * (svgW - 40) + 20;
            const yCoord = svgH - ((y - 1) / 4) * (svgH - 10) - 5;
            const isGhost = calls[i]?.ghost_resolved;
            return (
              <circle
                key={calls[i]?.call_id ?? i}
                cx={x} cy={yCoord} r="4"
                fill={isGhost ? "#ef4444" : "#3b82f6"}
                stroke="#18181b" strokeWidth="1.5"
                style={{ cursor: "pointer" }}
                onClick={() => nav(`/calls/${calls[i].call_id}`)}
              />
            );
          })}
        </svg>
        <p className="mt-1 text-[10px] text-zinc-600">Red dots = ghost resolutions. Click a dot to open the call.</p>
      </div>

      {/* Call list */}
      <div className="space-y-2">
        {calls.slice((callPage - 1) * PAGE_SIZE, callPage * PAGE_SIZE).map((c) => (
          <div
            key={c.call_id}
            onClick={() => nav(`/calls/${c.call_id}`)}
            className={`cursor-pointer rounded-lg border p-3 transition-colors hover:border-zinc-600 ${
              c.ghost_resolved ? "border-red-900 bg-zinc-900" : "border-zinc-800 bg-zinc-900"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs text-zinc-500">
                    {c.start_time_ms ? new Date(c.start_time_ms).toLocaleString() : "—"}
                  </span>
                  <span className="text-xs text-zinc-500">→ {c.agent_name}</span>
                  <span className="text-xs text-zinc-500">{c.duration_s?.toFixed(0)}s</span>
                </div>
                <p className="mt-1 text-sm text-zinc-300 truncate">{c.intent}</p>
                <p className="text-xs text-zinc-500 truncate">{c.summary}</p>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <AttentionScore score={c.attention_score} />
                <MoodBadge mood={c.mood_start} shift={!!c.mood_shift} direction={c.mood_shift_direction} />
                <ResolutionBadge
                  transcriptResolved={c.transcript_resolved}
                  behaviouralResolved={c.behavioural_resolved}
                  ghostResolved={c.ghost_resolved}
                  ghostGapMin={c.ghost_gap_min}
                />
              </div>
            </div>
          </div>
        ))}
        <Pagination page={callPage} total={calls.length} pageSize={PAGE_SIZE} onChange={setCallPage} />
      </div>
    </div>
  );
}
