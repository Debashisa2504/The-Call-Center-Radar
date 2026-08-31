import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import AudioPlayer from "../components/AudioPlayer.jsx";
import Transcript from "../components/Transcript.jsx";
import MoodTimeline from "../components/MoodTimeline.jsx";
import MoodBadge from "../components/MoodBadge.jsx";
import ResolutionBadge from "../components/ResolutionBadge.jsx";
import AttentionScore from "../components/AttentionScore.jsx";
import EmotionRadar from "../components/EmotionRadar.jsx";
import ComplianceBadges from "../components/ComplianceBadges.jsx";
import SuggestionCards from "../components/SuggestionCards.jsx";

export default function CallDetail() {
  const { callId } = useParams();
  const nav = useNavigate();
  const [call,        setCall]        = useState(null);
  const [compliance,  setCompliance]  = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [seekTo,      setSeekTo]      = useState(undefined);
  const [currentTime, setCurrentTime] = useState(0);
  const [loading,     setLoading]     = useState(true);
  const [evalRunning, setEvalRunning] = useState(false);
  const [ruleCount,   setRuleCount]   = useState(null);

  useEffect(() => {
    api.complianceRules().then(r => setRuleCount(Array.isArray(r) ? r.length : null)).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.call(callId),
      api.callCompliance(callId).catch(() => []),
      api.callSuggestions(callId).catch(() => ({ suggestions: [] })),
    ]).then(([c, comp, sugg]) => {
      setCall(c);
      setCompliance(Array.isArray(comp) ? comp : []);
      setSuggestions(sugg.suggestions || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [callId]);

  async function runComplianceEval() {
    setEvalRunning(true);
    // Snapshot old rule IDs so we can detect when fresh results arrive
    const prevIds = new Set(compliance.map(v => v.rule_id));
    try {
      await api.evaluateCompliance(callId);
    } catch (_) {
      setEvalRunning(false);
      return;
    }
    // Poll every 3s for up to 90s.
    // Fresh results detected when: count >= ruleCount OR rule IDs changed
    const start = Date.now();
    const poll = async () => {
      const comp = await api.callCompliance(callId).catch(() => []);
      const isFresh = Array.isArray(comp) && comp.length > 0 &&
        (comp.length >= (ruleCount || 1) ||
         comp.some(v => !prevIds.has(v.rule_id)) ||
         Date.now() - start > 30000);   // after 30s, accept whatever we have
      if (isFresh) {
        setCompliance(comp);
        setEvalRunning(false);
      } else if (Date.now() - start < 90000) {
        setTimeout(poll, 3000);
      } else {
        // Timeout — show whatever came back last (may be stale or empty)
        if (Array.isArray(comp) && comp.length > 0) setCompliance(comp);
        setEvalRunning(false);
      }
    };
    setTimeout(poll, 3000);
  }

  if (loading) return (
    <div className="flex h-64 items-center justify-center">
      <p className="animate-pulse font-mono text-sm text-zinc-500">Loading call…</p>
    </div>
  );
  if (!call) return <p className="text-red-400 p-8">Call not found.</p>;

  const customerEmotions = call.emotion_scores || {};
  const agentEmotions    = call.sentiment?.agent?.emotion_scores || {};
  const flaggedRules     = (Array.isArray(compliance) ? compliance : []).filter(v => v.had_violation);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <button onClick={() => nav(-1)} className="mb-2 font-mono text-xs text-zinc-500 hover:text-zinc-300">
            ← Back
          </button>
          <h1 className="text-lg font-semibold">{call.customer_name}</h1>
          <p className="font-mono text-xs text-zinc-500">
            Agent: {call.agent_name} · {call.duration_s?.toFixed(0)}s ·{" "}
            {call.start_time_ms ? new Date(call.start_time_ms).toLocaleString() : "—"}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <AttentionScore score={call.attention_score} />
          <MoodBadge mood={call.mood_start} shift={call.mood_shift} direction={call.mood_shift_direction} />
          <ResolutionBadge
            transcriptResolved={call.transcript_resolved}
            behaviouralResolved={call.behavioural_resolved}
            ghostResolved={call.ghost_resolved}
            ghostGapMin={call.ghost_gap_min}
          />
          {call.dominant_emotion && (
            <span className="rounded-full border border-zinc-700 bg-zinc-800 px-2 py-0.5 font-mono text-[11px] text-zinc-300 capitalize">
              😐 {call.dominant_emotion}
            </span>
          )}
        </div>
      </div>

      {/* Ghost alert */}
      {call.ghost_resolved && (
        <div className="rounded-lg border border-red-700 bg-red-950/50 p-4">
          <p className="font-semibold text-red-300">👻 Ghost Resolution Detected</p>
          <p className="mt-1 text-sm text-red-400">
            Agent said resolved — <strong>{call.customer_name}</strong> called back in{" "}
            <strong>{call.ghost_gap_min?.toFixed(1)} minutes</strong>.
          </p>
          {call.ghost_callback_id && (
            <button
              onClick={() => nav(`/calls/${call.ghost_callback_id}`)}
              className="mt-2 font-mono text-xs text-red-300 underline hover:text-red-100"
            >
              View callback call →
            </button>
          )}
        </div>
      )}

      {/* Compliance violations */}
      {flaggedRules.length > 0 && (
        <div className="rounded-lg border border-orange-800 bg-orange-950/30 p-4">
          <p className="font-semibold text-orange-300">⚠ Compliance Violations ({flaggedRules.length})</p>
          <div className="mt-2 space-y-3">
            {flaggedRules.map((v) => (
              <div key={v.rule_id} className="border-t border-orange-900/50 pt-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-orange-400">{v.rule_id}</span>
                  <span className="text-sm text-orange-200">{v.rule_name}</span>
                  <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
                    v.severity === "critical" ? "bg-red-900/60 text-red-200" :
                    v.severity === "high"     ? "bg-orange-900/60 text-orange-200" : "bg-amber-900/40 text-amber-200"
                  }`}>
                    {v.severity}
                  </span>
                </div>
                {(v.evidence?.violations || []).slice(0, 2).map((viol, i) => (
                  <div key={i} className="mt-1 rounded bg-zinc-900/60 p-2 text-xs">
                    <span className={viol.speaker === "Agent" ? "text-blue-400" : "text-green-400"}>
                      {viol.speaker}
                    </span>
                    <span className="text-zinc-500"> [{viol.timestamp}]</span>
                    <p className="mt-0.5 italic text-zinc-300">"{viol.quote}"</p>
                    <p className="mt-0.5 text-zinc-500">{viol.reasoning}</p>
                    {!viol.quote_verified && (
                      <span className="text-yellow-500 text-[10px]">⚠ quote not verified verbatim</span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Summary */}
      <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-4">
        <p className="mb-1 font-mono text-xs uppercase tracking-wide text-zinc-500">Summary</p>
        <p className="text-sm text-zinc-200">{call.summary}</p>
        <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
          <div><span className="text-zinc-500">Intent: </span><span className="text-zinc-200">{call.intent}</span></div>
          <div><span className="text-zinc-500">Attention: </span><span className="text-zinc-200">{call.attention_reason}</span></div>
          {call.sentiment?.overall?.summary && (
            <div className="col-span-2">
              <span className="text-zinc-500">Sentiment: </span>
              <span className="text-zinc-200">{call.sentiment.overall.summary}</span>
            </div>
          )}
          {call.trend_label && (
            <div>
              <span className="text-zinc-500">Cluster: </span>
              <span className="rounded bg-zinc-800 px-1 text-xs text-blue-300">{call.trend_label}</span>
            </div>
          )}
        </div>
        <SuggestionCards suggestions={suggestions} />
      </div>

      {/* Audio player */}
      <AudioPlayer
        src={api.audioUrl(callId)}
        seekTo={seekTo}
        onTimeUpdate={setCurrentTime}
      />

      {/* Three-column grid: mood + emotions + compliance actions */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <div className="space-y-4 lg:col-span-1">
          <MoodTimeline
            turns={call.transcript}
            moodShiftTimeS={call.mood_shift_time_s}
            moodStart={call.mood_start}
            moodShiftDirection={call.mood_shift_direction}
          />

          {/* 7-emotion radar (CortexV improvement) */}
          <EmotionRadar emotionScores={customerEmotions} label="Customer" />
          <EmotionRadar emotionScores={agentEmotions}    label="Agent" />

          {/* Evidence panel */}
          <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-3">
            <p className="mb-2 font-mono text-xs uppercase tracking-wide text-zinc-500">Evidence</p>
            <div className="space-y-2">
              {(call.evidence || []).map((e, i) => (
                <div
                  key={i}
                  onClick={() => setSeekTo({ t: e.timestamp_s, n: Date.now() })}
                  className="cursor-pointer rounded border border-zinc-700 bg-zinc-800 p-2 hover:border-blue-700 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] text-zinc-500">{e.judgment_type}</span>
                    <span className="font-mono text-[10px] text-blue-400">{e.timestamp_s?.toFixed(1)}s ▶</span>
                  </div>
                  <p className="mt-1 text-xs italic text-zinc-300">"{e.quote}"</p>
                  {e.reasoning && <p className="mt-0.5 text-[10px] text-zinc-500">{e.reasoning}</p>}
                </div>
              ))}
            </div>
          </div>

          {/* Compliance eval trigger */}
          <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-3">
            <p className="mb-2 font-mono text-xs uppercase tracking-wide text-zinc-500">Compliance</p>
            <button
              onClick={runComplianceEval}
              disabled={evalRunning}
              className="w-full rounded border border-zinc-600 bg-zinc-800 px-3 py-2 text-xs text-zinc-300 hover:border-orange-700 hover:text-orange-300 disabled:opacity-50 transition-colors"
            >
              {evalRunning ? "Evaluating rules…" : `⚖ Evaluate ${ruleCount ?? "…"} rules`}
            </button>
            <ComplianceBadges violations={compliance} />
          </div>
        </div>

        {/* Transcript */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-3 lg:col-span-3">
          <p className="mb-3 font-mono text-xs uppercase tracking-wide text-zinc-500">Transcript</p>
          <div className="max-h-[700px] overflow-y-auto">
            <Transcript
              turns={call.transcript}
              evidence={call.evidence}
              currentTime={currentTime}
              onSeek={setSeekTo}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
