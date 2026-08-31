const MOOD = {
  calm:        { label: "Calm",        cls: "bg-blue-900/50 text-blue-300 border-blue-700" },
  satisfied:   { label: "Satisfied",   cls: "bg-green-900/50 text-green-300 border-green-700" },
  confused:    { label: "Confused",    cls: "bg-amber-900/50 text-amber-300 border-amber-700" },
  frustrated:  { label: "Frustrated",  cls: "bg-orange-900/50 text-orange-300 border-orange-700" },
  angry:       { label: "Angry",       cls: "bg-red-900/50 text-red-300 border-red-700" },
};
export default function MoodBadge({ mood, shift, direction }) {
  const m = MOOD[mood] || { label: mood || "—", cls: "bg-zinc-800 text-zinc-400 border-zinc-700" };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${m.cls}`}>
      {m.label}
      {shift && (
        <span className={direction === "worsened" ? "text-red-400" : "text-green-400"}>
          {direction === "worsened" ? "↓" : "↑"}
        </span>
      )}
    </span>
  );
}
