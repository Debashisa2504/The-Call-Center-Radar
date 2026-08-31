export default function Pagination({ page, total, pageSize, onChange }) {
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
      <span className="font-mono text-xs text-zinc-500">
        {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}
      </span>
      <div className="flex gap-1">
        <button
          onClick={() => onChange(page - 1)}
          disabled={page === 1}
          className="rounded border border-zinc-700 px-2 py-1 font-mono text-xs text-zinc-400 hover:text-zinc-100 disabled:opacity-30 transition-colors"
        >
          ← Prev
        </button>
        {Array.from({ length: totalPages }, (_, i) => i + 1)
          .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
          .reduce((acc, p, idx, arr) => {
            if (idx > 0 && p - arr[idx - 1] > 1) acc.push("…");
            acc.push(p);
            return acc;
          }, [])
          .map((p, i) =>
            p === "…"
              ? <span key={`ellipsis-${i}`} className="px-1 font-mono text-xs text-zinc-600">…</span>
              : <button
                  key={p}
                  onClick={() => onChange(p)}
                  className={`rounded border px-2 py-1 font-mono text-xs transition-colors ${
                    p === page
                      ? "border-zinc-500 bg-zinc-700 text-zinc-100"
                      : "border-zinc-700 text-zinc-400 hover:text-zinc-100"
                  }`}
                >
                  {p}
                </button>
          )
        }
        <button
          onClick={() => onChange(page + 1)}
          disabled={page === totalPages}
          className="rounded border border-zinc-700 px-2 py-1 font-mono text-xs text-zinc-400 hover:text-zinc-100 disabled:opacity-30 transition-colors"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
