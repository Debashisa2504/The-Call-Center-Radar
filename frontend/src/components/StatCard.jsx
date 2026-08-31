export default function StatCard({ label, value, sub, color = "zinc", variant = "number" }) {
  const colors = {
    red:    "border-red-800 bg-red-950/40",
    green:  "border-green-800 bg-green-950/40",
    blue:   "border-blue-800 bg-blue-950/40",
    amber:  "border-amber-800 bg-amber-950/40",
    zinc:   "border-zinc-800 bg-zinc-900",
  };
  return (
    <div className={`rounded-lg border p-4 ${colors[color] || colors.zinc}`}>
      <p className="text-xs font-mono uppercase tracking-wide text-zinc-500">{label}</p>
      {variant === "text" ? (
        // Text-heavy stat (e.g. "Top issue") — the string itself is the
        // value, so it gets full-width, wrapping treatment instead of the
        // large truncated numeric style below, which was clipping and
        // burying the actual issue text.
        <p className="mt-1 text-sm font-semibold leading-snug text-zinc-100 break-words">
          {value}
        </p>
      ) : (
        <p className="mt-1 text-2xl font-semibold text-zinc-100">{value}</p>
      )}
      {sub && <p className="mt-0.5 text-xs text-zinc-500">{sub}</p>}
    </div>
  );
}
