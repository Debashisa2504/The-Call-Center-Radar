import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import StatCard from "../components/StatCard.jsx";
import Pagination from "../components/Pagination.jsx";

// ── Helpers ────────────────────────────────────────────────────────────────────

function scoreColor(score) {
  if (score >= 70) return "text-green-400";
  if (score >= 50) return "text-amber-400";
  return "text-red-400";
}

function scoreBg(score) {
  if (score >= 70) return "bg-green-900/40 border-green-700";
  if (score >= 50) return "bg-amber-900/40 border-amber-700";
  return "bg-red-900/40 border-red-700";
}

function emotionColor(emotion) {
  const map = {
    frustrated: "text-red-400",
    angry: "text-red-500",
    anxious: "text-orange-400",
    satisfied: "text-green-400",
    happy: "text-green-300",
    engaged: "text-blue-400",
    neutral: "text-zinc-400",
    calm: "text-zinc-400",
  };
  return map[emotion] || "text-zinc-400";
}

function RankMedal({ rank }) {
  if (rank === 1) return <span className="text-xl">🥇</span>;
  if (rank === 2) return <span className="text-xl">🥈</span>;
  if (rank === 3) return <span className="text-xl">🥉</span>;
  return <span className="font-mono text-sm text-zinc-500">#{rank}</span>;
}

function DateRangePicker({ from, to, onChange }) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="date"
        value={from}
        onChange={e => onChange(e.target.value, to)}
        className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 font-mono text-xs text-zinc-200 focus:border-blue-600 focus:outline-none"
      />
      <span className="font-mono text-xs text-zinc-500">–</span>
      <input
        type="date"
        value={to}
        onChange={e => onChange(from, e.target.value)}
        className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 font-mono text-xs text-zinc-200 focus:border-blue-600 focus:outline-none"
      />
      {(from || to) && (
        <button
          onClick={() => onChange("", "")}
          className="font-mono text-xs text-zinc-500 hover:text-zinc-300"
        >
          Clear
        </button>
      )}
    </div>
  );
}

function ScoreBar({ score, max = 100 }) {
  const pct = Math.min(100, (score / max) * 100);
  const color = score >= 70 ? "bg-green-500" : score >= 50 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="h-1.5 w-full rounded-full bg-zinc-800">
      <div className={`h-1.5 rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
    </div>
  );
}

// ── Issue expansion panel ────────────────────────────────────────────────
// Lazy-fetches GET /dashboard/issues/{intent}/detail on first expand and
// caches the result in the parent so re-toggling doesn't re-fetch.

function IssueDetailPanel({ intent, cache, setCache }) {
  const [loading, setLoading] = useState(!cache[intent]);
  const [error, setError]     = useState(null);

  useEffect(() => {
    if (cache[intent]) { setLoading(false); return; }
    setLoading(true);
    setError(null);
    api.issueDetail(intent)
      .then(d => { setCache(prev => ({ ...prev, [intent]: d })); setLoading(false); })
      .catch(() => { setError("Couldn't load detail for this issue."); setLoading(false); });
  }, [intent]); // eslint-disable-line react-hooks/exhaustive-deps

  const detail = cache[intent];

  if (loading) return <p className="mt-3 animate-pulse text-xs text-zinc-500">Loading suggestion…</p>;
  if (error)   return <p className="mt-3 text-xs text-red-400">{error}</p>;
  if (!detail) return null;

  return (
    <div className="mt-3 space-y-3 border-t border-zinc-800 pt-3">
      <div className="rounded-md border border-blue-900/50 bg-blue-950/20 p-3">
        <p className="font-mono text-[10px] uppercase tracking-wide text-blue-400">Suggested fix</p>
        <p className="mt-1 text-xs text-zinc-300">{detail.suggestion}</p>
      </div>

      {detail.dissatisfied_calls?.length > 0 && (
        <div>
          <p className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
            What caused the dissatisfaction ({detail.dissatisfied_calls.length})
          </p>
          <div className="space-y-1.5">
            {detail.dissatisfied_calls.slice(0, 8).map(c => (
              <div key={c.call_id} className="flex items-start justify-between gap-3 rounded bg-zinc-950/50 px-2.5 py-1.5">
                <div className="min-w-0">
                  <span className="text-xs font-medium text-zinc-300">{c.customer_name}</span>
                  <span className="ml-2 text-[11px] text-zinc-500">{c.summary}</span>
                </div>
                <span className={`shrink-0 text-[11px] font-medium ${emotionColor(c.dominant_emotion)}`}>
                  {c.dominant_emotion}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tabs ───────────────────────────────────────────────────────────────────────

const TAB = {
  ISSUES:       "issues",
  SATISFACTION: "satisfaction",
  PERFORMANCE:  "performance",
  FLAGS:        "flags",
};

const PAGE_SIZE = 10;

// ── Page ───────────────────────────────────────────────────────────────────────

export default function CustomerPerception() {
  const nav = useNavigate();
  const [tab, setTab]             = useState(TAB.ISSUES);
  const [issFrom, setIssFrom]     = useState("");
  const [issTo,   setIssTo]       = useState("");
  const [satFrom, setSatFrom]     = useState("");
  const [satTo,   setSatTo]       = useState("");

  const [issues,       setIssues]       = useState([]);
  const [satisfaction, setSatisfaction] = useState(null);
  const [performance,  setPerformance]  = useState([]);
  const [rudeAgents,   setRudeAgents]   = useState([]);
  const [spamCallers,  setSpamCallers]  = useState([]);
  const [loading,      setLoading]      = useState(true);

  // Pagination state
  const [issuesPage,  setIssuesPage]  = useState(1);
  const [satPage,     setSatPage]     = useState(1);
  const [perfPage,    setPerfPage]    = useState(1);
  const [spamPage,    setSpamPage]    = useState(1);

  const [expandedIssue, setExpandedIssue]       = useState(null);
  const [issueDetailCache, setIssueDetailCache] = useState({});
  const [topIssueSuggestion, setTopIssueSuggestion] = useState(null);

  // Initial load — all 5 endpoints in parallel
  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      api.issueFrequency(),
      api.satisfaction(),
      api.agentPerformance(),
      api.rudeAgents(),
      api.spamCallers(),
    ]).then(([iss, sat, perf, rude, spam]) => {
      const v = r => r.status === "fulfilled" ? r.value : null;
      const issueList = Array.isArray(v(iss)) ? v(iss) : [];
      setIssues(issueList);
      setSatisfaction(v(sat));
      setPerformance(Array.isArray(v(perf)) ? v(perf) : []);
      setRudeAgents(Array.isArray(v(rude)) ? v(rude) : []);
      const spamData = v(spam);
      setSpamCallers(Array.isArray(spamData?.callers) ? spamData.callers : []);
      setLoading(false);
      // Auto-fetch suggestion for the #1 issue
      if (issueList[0]?.intent) {
        api.issueDetail(issueList[0].intent)
          .then(d => setTopIssueSuggestion(d))
          .catch(() => {});
      }
    }).catch(err => {
      console.error("Perception data load failed:", err);
      setLoading(false);
    });
  }, []);

  // Reload issues on date range change
  const fetchIssues = useCallback((from, to) => {
    api.issueFrequency(from, to)
      .then(d => { setIssues(Array.isArray(d) ? d : []); setIssuesPage(1); setExpandedIssue(null); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (loading) return;
    fetchIssues(issFrom, issTo);
  }, [issFrom, issTo]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reload satisfaction on date range change
  const fetchSatisfaction = useCallback((from, to) => {
    api.satisfaction(from, to)
      .then(d => { setSatisfaction(d); setSatPage(1); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (loading) return;
    fetchSatisfaction(satFrom, satTo);
  }, [satFrom, satTo]); // eslint-disable-line react-hooks/exhaustive-deps

  const flaggedAgents = rudeAgents.filter(a => a.flagged).length;
  const flaggedSpam   = spamCallers.filter(s => s.flagged).length;
  const topPerformers = performance.slice(0, 3);

  // Paginated slices
  const issuesPage_data = issues.slice((issuesPage - 1) * PAGE_SIZE, issuesPage * PAGE_SIZE);
  const satCalls        = satisfaction?.calls || [];
  const satPage_data    = satCalls.slice((satPage - 1) * PAGE_SIZE, satPage * PAGE_SIZE);
  const perfPage_data   = performance.slice((perfPage - 1) * PAGE_SIZE, perfPage * PAGE_SIZE);
  const spamPage_data   = spamCallers.slice((spamPage - 1) * PAGE_SIZE, spamPage * PAGE_SIZE);

  if (loading) return (
    <div className="flex h-64 items-center justify-center">
      <p className="animate-pulse font-mono text-sm text-zinc-500">Loading perception data…</p>
    </div>
  );

  return (
    <div className="space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Customer Perception</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Issue frequency · Satisfaction tracking · Agent performance · Behavioural flags
        </p>
      </div>

      {/* Summary stat cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard
          label="Dissatisfied customers"
          value={satisfaction?.dissatisfied_count ?? "—"}
          sub={`${satisfaction?.dissatisfied_rate_pct ?? 0}% of calls`}
          color={satisfaction?.dissatisfied_rate_pct > 30 ? "red" : "amber"}
        />
        <StatCard
          label="Agents flagged"
          value={flaggedAgents}
          sub="Behaviour concerns"
          color={flaggedAgents > 0 ? "red" : "green"}
        />
        <StatCard
          label="Spam / trivial callers"
          value={flaggedSpam}
          sub="Low-intent pattern"
          color={flaggedSpam > 3 ? "amber" : "zinc"}
        />
      </div>

      {/* Top Issue Spotlight — always visible with AI suggestion */}
      {issues[0] && (
        <div className="rounded-xl border border-amber-700/60 bg-amber-950/20 p-5">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-wide text-amber-400">🔥 #1 Issue — {issues[0].call_count} calls</p>
              <h2 className="mt-1 text-base font-semibold text-amber-100">{issues[0].intent}</h2>
              <div className="mt-1 flex gap-4 text-xs text-zinc-400">
                {issues[0].dissatisfied_count > 0 && (
                  <span className="text-red-400">😤 {issues[0].dissatisfied_count} dissatisfied</span>
                )}
                {issues[0].ghost_rate_pct > 0 && (
                  <span className="text-orange-400">👻 {issues[0].ghost_rate_pct}% ghost rate</span>
                )}
                <span>Resolved: <span className="text-green-400">{issues[0].true_resolution_pct}%</span></span>
              </div>
            </div>
          </div>
          <div className="mt-4 rounded-lg border border-blue-800/50 bg-blue-950/30 p-3">
            <p className="font-mono text-[10px] uppercase tracking-wide text-blue-400">💡 Suggested Fix</p>
            {topIssueSuggestion
              ? <p className="mt-1 text-sm text-zinc-200">{topIssueSuggestion.suggestion}</p>
              : <p className="mt-1 animate-pulse text-xs text-zinc-500">Loading suggestion…</p>
            }
          </div>
        </div>
      )}

      {/* Leaderboard hero — top 3 */}
      {topPerformers.length > 0 && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
          <h2 className="mb-4 font-mono text-xs uppercase tracking-wide text-zinc-500">
            🏆 Performance Leaderboard — Top Experts
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {topPerformers.map(agent => (
              <div key={agent.agent_name} className={`rounded-lg border p-4 ${scoreBg(agent.performance_score)}`}>
                <div className="flex items-center gap-2">
                  <RankMedal rank={agent.rank} />
                  <span className="font-semibold text-sm truncate">{agent.agent_name}</span>
                </div>
                <div className="mt-3">
                  <div className="flex items-end justify-between">
                    <span className={`text-2xl font-bold font-mono ${scoreColor(agent.performance_score)}`}>
                      {agent.performance_score}
                    </span>
                    <span className="text-xs text-zinc-500">/ 100</span>
                  </div>
                  <ScoreBar score={agent.performance_score} />
                </div>
                <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-zinc-400">
                  <span>Resolved: <span className="text-green-400 font-mono">{agent.true_resolution_pct}%</span></span>
                  <span>Ghost: <span className="text-red-400 font-mono">{agent.ghost_rate_pct}%</span></span>
                  <span>Calls: <span className="text-zinc-300 font-mono">{agent.total_calls}</span></span>
                  <span>+ve: <span className="text-zinc-300 font-mono">{agent.positive_outcome_pct}%</span></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-zinc-800">
        {[
          { k: TAB.ISSUES,       label: "📋 Issue Frequency" },
          { k: TAB.SATISFACTION, label: "😤 Satisfaction" },
          { k: TAB.PERFORMANCE,  label: "🎯 Full Performance" },
          { k: TAB.FLAGS,        label: `🚩 Flags (${flaggedAgents} agents · ${flaggedSpam} callers)` },
        ].map(({ k, label }) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`mr-1 rounded-t-md px-4 py-2 font-mono text-xs uppercase tracking-wide transition-colors ${
              tab === k
                ? "border border-b-0 border-zinc-700 bg-zinc-900 text-zinc-100"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Issue Frequency ──────────────────────────────────────────────────── */}
      {tab === TAB.ISSUES && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-xs text-zinc-500">
              Most common reasons customers called — ranked by volume.
            </p>
            <DateRangePicker from={issFrom} to={issTo} onChange={(f,t) => { setIssFrom(f); setIssTo(t); }} />
          </div>

          {issues.length === 0 ? (
            <p className="text-sm text-zinc-500">No data for this period yet.</p>
          ) : (
            <>
              <div className="space-y-2">
                {issuesPage_data.map((issue, i) => {
                  const globalIdx = (issuesPage - 1) * PAGE_SIZE + i;
                  const maxCount  = issues[0]?.call_count || 1;
                  const barPct    = (issue.call_count / maxCount) * 100;
                  const isOpen    = expandedIssue === issue.intent;
                  return (
                    <div key={issue.intent} className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
                      <div
                        className="flex items-start gap-4 cursor-pointer"
                        onClick={() => setExpandedIssue(isOpen ? null : issue.intent)}
                      >
                        <span className="font-mono text-2xl font-bold text-zinc-600 w-8 shrink-0">
                          {globalIdx + 1}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <span className="font-medium text-sm">{issue.intent}</span>
                            <div className="flex items-center gap-3 shrink-0">
                              <span className="font-mono text-xs font-semibold text-zinc-300">
                                ({issue.call_count} calls)
                              </span>
                              {issue.ghost_rate_pct > 0 && (
                                <span className="text-xs text-red-400">{issue.ghost_rate_pct}% ghost</span>
                              )}
                              <span className="text-xs text-zinc-500">
                                {isOpen ? "▲ hide" : "▼ see suggestion"}
                              </span>
                            </div>
                          </div>
                          <div className="mt-2 h-1.5 w-full rounded-full bg-zinc-800">
                            <div className="h-1.5 rounded-full bg-blue-500 transition-all" style={{ width: `${barPct}%` }} />
                          </div>
                          <div className="mt-1.5 flex gap-4 text-xs text-zinc-500">
                            <span>Resolved: <span className="text-green-400">{issue.true_resolution_pct}%</span></span>
                            <span>Claimed: <span className="text-zinc-400">{issue.claimed_resolution_pct}%</span></span>
                            <span>Avg attention: <span className="text-zinc-400">{issue.avg_attention}</span></span>
                            {issue.dissatisfied_count > 0 && (
                              <span className="text-red-400">😤 {issue.dissatisfied_count} dissatisfied</span>
                            )}
                          </div>
                        </div>
                      </div>
                      {isOpen && (
                        <IssueDetailPanel
                          intent={issue.intent}
                          cache={issueDetailCache}
                          setCache={setIssueDetailCache}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
              <Pagination page={issuesPage} total={issues.length} pageSize={PAGE_SIZE} onChange={setIssuesPage} />
            </>
          )}
        </div>
      )}

      {/* ── Satisfaction ─────────────────────────────────────────────────────── */}
      {tab === TAB.SATISFACTION && (
        <div className="space-y-4">
          {!satisfaction ? (
            <p className="text-sm text-zinc-500">No satisfaction data available.</p>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-2xl font-bold font-mono text-red-400">
                    {satisfaction.dissatisfied_count}
                  </span>
                  <span className="ml-2 text-sm text-zinc-400">
                    dissatisfied customers ({satisfaction.dissatisfied_rate_pct}% of {satisfaction.total_calls} calls)
                  </span>
                </div>
                <DateRangePicker from={satFrom} to={satTo} onChange={(f,t) => { setSatFrom(f); setSatTo(t); }} />
              </div>

              {/* Daily trend mini-chart */}
              {(satisfaction.daily_trend || []).length > 0 && (
                <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
                  <p className="mb-3 font-mono text-xs uppercase tracking-wide text-zinc-500">Daily trend</p>
                  <div className="flex items-end gap-2 h-16">
                    {[...(satisfaction.daily_trend || [])].reverse().map((d, i) => {
                      const rate = d.total > 0 ? d.dissatisfied / d.total : 0;
                      const h    = Math.max(4, rate * 100);
                      return (
                        <div key={i} className="flex flex-1 flex-col items-center gap-1">
                          <div
                            className="w-full rounded-sm bg-red-500/70 transition-all"
                            style={{ height: `${h}%` }}
                            title={`${d.day}: ${d.dissatisfied}/${d.total} dissatisfied`}
                          />
                          <span className="font-mono text-[9px] text-zinc-600">{d.day?.slice(5)}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Dissatisfied call list */}
              <div className="space-y-2">
                <p className="text-xs text-zinc-500">
                  {satCalls.length} calls with frustrated / angry / anxious emotion or negative sentiment
                </p>
                {satPage_data.map(call => (
                  <div
                    key={call.call_id}
                    onClick={() => nav(`/calls/${call.call_id}`)}
                    className="cursor-pointer rounded-lg border border-zinc-800 bg-zinc-900 p-4 hover:border-zinc-600 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-semibold text-sm">{call.customer_name}</span>
                          <span className="text-zinc-500 text-xs">→ {call.agent_name}</span>
                          {call.dominant_emotion && (
                            <span className={`text-xs font-medium ${emotionColor(call.dominant_emotion)}`}>
                              {call.dominant_emotion}
                            </span>
                          )}
                          {call.ghost_resolved ? (
                            <span className="rounded-full bg-red-900/60 border border-red-700 px-2 py-0.5 text-xs text-red-300">
                              👻 ghost
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-1 text-xs text-zinc-400 truncate">{call.intent}</p>
                        <p className="mt-0.5 text-xs text-zinc-500 truncate">{call.summary}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <span className={`font-mono text-sm font-semibold ${
                          call.attention_score > 70 ? "text-red-400" :
                          call.attention_score > 40 ? "text-amber-400" : "text-zinc-400"
                        }`}>
                          {call.attention_score}
                        </span>
                        <p className="text-[10px] text-zinc-600">attn</p>
                      </div>
                    </div>
                  </div>
                ))}
                <Pagination page={satPage} total={satCalls.length} pageSize={PAGE_SIZE} onChange={setSatPage} />
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Full Performance Table ────────────────────────────────────────────── */}
      {tab === TAB.PERFORMANCE && (
        <div className="space-y-4">
          <p className="text-xs text-zinc-500">
            Score = 40% true resolution + 25% (1 − ghost rate) + 20% customer sentiment + 15% low attention.
          </p>
          {performance.length === 0 ? (
            <p className="text-sm text-zinc-500">No performance data yet.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-800 text-left font-mono text-xs uppercase tracking-wide text-zinc-500">
                      <th className="pb-2 pr-3">Rank</th>
                      <th className="pb-2 pr-4">Agent</th>
                      <th className="pb-2 pr-4 text-right">Score</th>
                      <th className="pb-2 pr-4 text-right text-green-400">True Resolved</th>
                      <th className="pb-2 pr-4 text-right text-red-400">Ghost Rate</th>
                      <th className="pb-2 pr-4 text-right">+ve Outcomes</th>
                      <th className="pb-2 pr-4 text-right">Calls</th>
                      <th className="pb-2 text-right">Avg Duration</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/50">
                    {perfPage_data.map(agent => (
                      <tr key={agent.agent_name} className="hover:bg-zinc-900 transition-colors">
                        <td className="py-2.5 pr-3"><RankMedal rank={agent.rank} /></td>
                        <td className="py-2.5 pr-4 font-medium">{agent.agent_name}</td>
                        <td className="py-2.5 pr-4 text-right">
                          <span className={`font-mono font-bold ${scoreColor(agent.performance_score)}`}>
                            {agent.performance_score}
                          </span>
                          <ScoreBar score={agent.performance_score} />
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono text-green-400">{agent.true_resolution_pct}%</td>
                        <td className="py-2.5 pr-4 text-right font-mono text-red-400">{agent.ghost_rate_pct}%</td>
                        <td className="py-2.5 pr-4 text-right font-mono text-zinc-400">{agent.positive_outcome_pct}%</td>
                        <td className="py-2.5 pr-4 text-right font-mono text-zinc-400">{agent.total_calls}</td>
                        <td className="py-2.5 text-right font-mono text-zinc-400">{agent.avg_duration_s?.toFixed(0)}s</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={perfPage} total={performance.length} pageSize={PAGE_SIZE} onChange={setPerfPage} />
            </>
          )}
        </div>
      )}

      {/* ── Flags ────────────────────────────────────────────────────────────── */}
      {tab === TAB.FLAGS && (
        <div className="space-y-8">

          {/* Rude / problematic agents */}
          <div>
            <h3 className="mb-3 font-mono text-xs uppercase tracking-wide text-zinc-500 flex items-center gap-2">
              <span>⚠ Agent Behaviour Flags</span>
              {flaggedAgents > 0 && (
                <span className="rounded-full bg-red-900/60 border border-red-700 px-2 py-0.5 text-red-300">
                  {flaggedAgents} flagged
                </span>
              )}
            </h3>
            <p className="mb-3 text-xs text-zinc-600">
              Based on: customer mood worsening during call, high negative emotion rate, elevated attention scores.
            </p>
            {rudeAgents.length === 0 ? (
              <p className="text-sm text-zinc-500">No agents flagged yet — more data needed.</p>
            ) : (
              <div className="space-y-2">
                {rudeAgents.map(agent => (
                  <div
                    key={agent.agent_name}
                    className={`rounded-lg border p-4 ${
                      agent.flagged ? "border-red-800 bg-red-950/20" : "border-zinc-800 bg-zinc-900"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          {agent.flagged && <span className="text-red-400 text-sm">🚩</span>}
                          <span className="font-semibold text-sm">{agent.agent_name}</span>
                          <span className="text-zinc-500 text-xs">{agent.total_calls} calls</span>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
                          <span className="text-zinc-500">
                            Mood worsened: <span className={agent.worsened_mood_pct > 30 ? "text-red-400 font-mono" : "text-zinc-400 font-mono"}>{agent.worsened_mood_pct}%</span>
                          </span>
                          <span className="text-zinc-500">
                            Neg emotion: <span className={agent.neg_emotion_pct > 40 ? "text-red-400 font-mono" : "text-zinc-400 font-mono"}>{agent.neg_emotion_pct}%</span>
                          </span>
                          <span className="text-zinc-500">
                            Ghost rate: <span className="text-zinc-400 font-mono">{agent.ghost_rate_pct}%</span>
                          </span>
                          <span className="text-zinc-500">
                            High-attn calls: <span className="text-zinc-400 font-mono">{agent.high_attention_calls}</span>
                          </span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <span className={`text-xl font-bold font-mono ${
                          agent.rudeness_score > 30 ? "text-red-400" :
                          agent.rudeness_score > 15 ? "text-amber-400" : "text-zinc-400"
                        }`}>
                          {agent.rudeness_score}
                        </span>
                        <p className="text-[10px] text-zinc-600">risk score</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Spam / trivial callers */}
          <div>
            <h3 className="mb-3 font-mono text-xs uppercase tracking-wide text-zinc-500 flex items-center gap-2">
              <span>🔇 Potential Spam / Trivial Callers</span>
              {flaggedSpam > 0 && (
                <span className="rounded-full bg-amber-900/60 border border-amber-700 px-2 py-0.5 text-amber-300">
                  {flaggedSpam} flagged
                </span>
              )}
            </h3>
            <p className="mb-3 text-xs text-zinc-600">
              Callers repeatedly contacting about self-service issues (balance, branch hours, password reset) that could be resolved digitally.
            </p>
            {spamCallers.length === 0 ? (
              <p className="text-sm text-zinc-500">No suspicious callers detected yet.</p>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-800 text-left font-mono text-xs uppercase tracking-wide text-zinc-500">
                        <th className="pb-2 pr-4">Customer</th>
                        <th className="pb-2 pr-4 text-right">Calls</th>
                        <th className="pb-2 pr-4 text-right">Self-service calls</th>
                        <th className="pb-2 pr-4 text-right">Repeat rate</th>
                        <th className="pb-2 pr-4 text-right">Avg duration</th>
                        <th className="pb-2 text-right">Trivial score</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800/50">
                      {spamPage_data.map(c => (
                        <tr
                          key={c.customer_name}
                          onClick={() => nav(`/customers/${encodeURIComponent(c.customer_name)}`)}
                          className="cursor-pointer hover:bg-zinc-900 transition-colors"
                        >
                          <td className="py-2.5 pr-4 font-medium">
                            {c.flagged && <span className="text-amber-400 mr-1">⚠</span>}
                            {c.customer_name}
                          </td>
                          <td className="py-2.5 pr-4 text-right font-mono text-zinc-400">{c.total_calls}</td>
                          <td className="py-2.5 pr-4 text-right font-mono text-amber-400">
                            {c.self_service_calls} <span className="text-zinc-600">({c.self_service_pct}%)</span>
                          </td>
                          <td className="py-2.5 pr-4 text-right font-mono text-zinc-400">{c.repeat_rate_pct}%</td>
                          <td className="py-2.5 pr-4 text-right font-mono text-zinc-400">{c.avg_duration_s}s</td>
                          <td className="py-2.5 text-right">
                            <span className={`font-mono font-semibold ${
                              c.spam_score > 50 ? "text-red-400" :
                              c.spam_score > 30 ? "text-amber-400" : "text-zinc-400"
                            }`}>
                              {c.spam_score}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination page={spamPage} total={spamCallers.length} pageSize={PAGE_SIZE} onChange={setSpamPage} />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
