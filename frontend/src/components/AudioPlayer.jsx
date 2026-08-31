import { useRef, useState, useEffect } from "react";

export default function AudioPlayer({ src, seekTo, onTimeUpdate }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

  // seekTo is { t: number, n: nonce } so clicking the same timestamp twice still seeks
  useEffect(() => {
    if (seekTo != null && audioRef.current) {
      const t = typeof seekTo === "object" ? seekTo.t : seekTo;
      if (t != null) {
        audioRef.current.currentTime = t;
        audioRef.current.play();
        setPlaying(true);
      }
    }
  }, [seekTo]);

  const fmt = (s) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  const pct = duration ? (current / duration) * 100 : 0;

  return (
    <div className="flex items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-900 p-3">
      <audio
        ref={audioRef}
        src={src}
        onTimeUpdate={(e) => {
          setCurrent(e.target.currentTime);
          onTimeUpdate?.(e.target.currentTime);
        }}
        onLoadedMetadata={(e) => setDuration(e.target.duration)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
      <button
        onClick={() => {
          if (playing) { audioRef.current.pause(); }
          else { audioRef.current.play(); }
        }}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-600 text-white hover:bg-blue-500 transition-colors"
      >
        {playing ? "⏸" : "▶"}
      </button>
      <div className="flex-1">
        <div
          className="relative h-1.5 cursor-pointer rounded-full bg-zinc-700"
          onClick={(e) => {
            if (!audioRef.current || !duration) return;
            const rect = e.currentTarget.getBoundingClientRect();
            const p = (e.clientX - rect.left) / rect.width;
            audioRef.current.currentTime = p * duration;
            audioRef.current.play();
          }}
        >
          <div className="absolute left-0 top-0 h-full rounded-full bg-blue-500" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-1 flex justify-between font-mono text-[11px] text-zinc-500">
          <span>{fmt(current)}</span>
          <span>{fmt(duration)}</span>
        </div>
      </div>
    </div>
  );
}
