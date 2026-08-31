/**
 * ComplianceBadges.jsx
 * ----------------------
 * Shows compact compliance rule violation indicators for a call.
 * Used in CallDetail and the attention queue rows.
 *
 * Props:
 *   violations: [{rule_id, rule_name, severity, had_violation, violations:[...]}]
 */

const SEV_COLOR = {
  critical: "bg-red-900/70 border-red-600 text-red-200",
  high:     "bg-orange-900/60 border-orange-700 text-orange-200",
  medium:   "bg-amber-900/50 border-amber-700 text-amber-200",
  low:      "bg-zinc-800 border-zinc-600 text-zinc-300",
};

export default function ComplianceBadges({ violations = [] }) {
  const flagged = violations.filter((v) => v.had_violation);

  if (violations.length === 0) return null;

  if (flagged.length === 0) {
    return (
      <div className="mt-2 rounded border border-green-800 bg-green-950/40 px-2 py-1.5 font-mono text-[11px] text-green-400">
        ✓ All {violations.length} rules passed
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-1 mt-2">
      {flagged.map((v) => (
        <span
          key={v.rule_id}
          title={v.rule_description || v.rule_name}
          className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px] ${SEV_COLOR[v.severity] || SEV_COLOR.low}`}
        >
          ⚠ {v.rule_name || v.rule_id}
        </span>
      ))}
    </div>
  );
}
