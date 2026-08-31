export default function MoodTimeline({ turns, moodShiftTimeS, moodStart, moodShiftDirection }) {
  const MOOD_Y = { satisfied: 10, calm: 25, confused: 45, frustrated: 65, angry: 85 };
  const totalDuration = Math.max(1, turns?.length ? (turns[turns.length - 1]?.end_s || 1) : 1);

  if (!turns?.length) return null;

  const shiftX = moodShiftTimeS
    ? (moodShiftTimeS / totalDuration) * 280
    : null;

  const startY = MOOD_Y[moodStart] ?? 25;
  const endY = moodShiftTimeS
    ? moodShiftDirection === "worsened" ? 75 : 15
    : startY;

  const points = moodShiftTimeS
    ? `20,${startY} ${shiftX + 20},${startY} 300,${endY}`
    : `20,${startY} 300,${startY}`;

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-3">
      <p className="mb-2 text-xs font-mono uppercase tracking-wide text-zinc-500">Mood timeline</p>
      <svg width="100%" viewBox="0 0 320 100">
        {["satisfied", "calm", "confused", "frustrated", "angry"].map((m) => (
          <text key={m} x="2" y={MOOD_Y[m] + 4} fontSize="9" fill="#52525b">
            {m}
          </text>
        ))}
        <polyline points={points} fill="none" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round" />
        {shiftX != null && (
          <>
            <line x1={shiftX + 20} y1="0" x2={shiftX + 20} y2="100"
              stroke="#ef4444" strokeWidth="1" strokeDasharray="3 2" />
            <text x={shiftX + 23} y="12" fontSize="9" fill="#ef4444">shift</text>
          </>
        )}
      </svg>
    </div>
  );
}
