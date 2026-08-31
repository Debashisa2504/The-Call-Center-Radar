/**
 * EmotionRadar.jsx
 * -----------------
 * Renders the 7-emotion vector as a small radar/bar chart.
 * Used in the CallDetail mood panel and the AgentView emotion breakdown.
 *
 * Props:
 *   emotionScores: {engaged:0.3, frustrated:0.5, anxious:0.2, ...}
 *   label: "Customer" | "Agent"
 */

const EMOTIONS = [
  { key: "engaged",      color: "#3b82f6" },
  { key: "enthusiastic", color: "#22c55e" },
  { key: "happy",        color: "#86efac" },
  { key: "neutral",      color: "#6b7280" },
  { key: "concerned",    color: "#f59e0b" },
  { key: "anxious",      color: "#f97316" },
  { key: "frustrated",   color: "#ef4444" },
];

export default function EmotionRadar({ emotionScores = {}, label = "" }) {
  if (!emotionScores || Object.keys(emotionScores).length === 0) return null;

  const total = Object.values(emotionScores).reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-3">
      {label && (
        <p className="mb-2 font-mono text-[11px] uppercase tracking-wide text-zinc-500">
          {label} emotions
        </p>
      )}
      <div className="space-y-1.5">
        {EMOTIONS.map(({ key, color }) => {
          const val = emotionScores[key] || 0;
          const pct = Math.round((val / total) * 100);
          if (pct < 1) return null;
          return (
            <div key={key} className="flex items-center gap-2">
              <span className="w-20 text-right font-mono text-[10px] text-zinc-400 capitalize">
                {key}
              </span>
              <div className="flex-1 h-2 rounded-full bg-zinc-800">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${pct}%`, backgroundColor: color }}
                />
              </div>
              <span className="w-8 font-mono text-[10px] text-zinc-500">
                {pct}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
