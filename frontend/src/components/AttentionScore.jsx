export default function AttentionScore({ score }) {
  const color =
    score >= 75 ? "text-red-400 bg-red-900/30 border-red-700" :
    score >= 50 ? "text-orange-400 bg-orange-900/30 border-orange-700" :
    score >= 25 ? "text-amber-400 bg-amber-900/30 border-amber-700" :
                  "text-zinc-500 bg-zinc-800 border-zinc-700";
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 font-mono text-sm font-semibold ${color}`}>
      {score ?? "—"}
    </span>
  );
}
