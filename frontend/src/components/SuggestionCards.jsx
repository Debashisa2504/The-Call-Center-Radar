import { useState } from "react";

export default function SuggestionCards({ suggestions = [], onSelect }) {
  const [copied, setCopied] = useState(null);

  if (!suggestions.length) return null;

  function handleClick(s) {
    if (onSelect) { onSelect(s); return; }
    navigator.clipboard?.writeText(s)
      .then(() => {
        setCopied(s);
        setTimeout(() => setCopied(null), 1500);
      })
      .catch(() => {
        // clipboard denied — still show feedback
        setCopied(s);
        setTimeout(() => setCopied(null), 1500);
      });
  }

  return (
    <div className="mt-3 space-y-1">
      <p className="font-mono text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
        Suggested follow-ups
      </p>
      {suggestions.map((s, i) => (
        <button
          key={i}
          onClick={() => handleClick(s)}
          className="w-full rounded border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-left text-xs text-zinc-300 hover:border-blue-700 hover:text-blue-200 transition-colors"
        >
          {copied === s ? "✓ Copied" : `→ ${s}`}
        </button>
      ))}
    </div>
  );
}
