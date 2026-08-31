export default function ResolutionBadge({ transcriptResolved, behaviouralResolved, ghostResolved, ghostGapMin }) {
  if (ghostResolved) {
    return (
      <span className="ghost-badge inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium">
        👻 Ghost ({ghostGapMin?.toFixed(0)}m)
      </span>
    );
  }
  if (behaviouralResolved) {
    return (
      <span className="resolved-badge inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium">
        ✓ Resolved
      </span>
    );
  }
  if (transcriptResolved) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-yellow-700 bg-yellow-900/50 px-2 py-0.5 text-xs font-medium text-yellow-300">
        ? Claimed
      </span>
    );
  }
  return (
    <span className="unresolved-badge inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium">
      ✗ Unresolved
    </span>
  );
}
