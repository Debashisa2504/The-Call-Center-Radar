import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import StatCard from "../components/StatCard.jsx";
import AttentionScore from "../components/AttentionScore.jsx";
import MoodBadge from "../components/MoodBadge.jsx";
import ResolutionBadge from "../components/ResolutionBadge.jsx";
import Pagination from "../components/Pagination.jsx";

const TAB = { ATTENTION: "attention", GHOST: "ghost", TRENDS: "trends", AGENTS: "agents" };
const PAGE_SIZE = 10;

export default function Dashboard() {
  const nav = useNavigate();
  const [tab, setTab]       = useState(TAB.GHOST);
  const [stats, setStats]   = useState(null);
  const [attention, setAttention] = useState([]);
  const [ghost, setGhost]   = useState([]);
  const [trends, setTrends] = useState(null);
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(false);

  const [ghostPage,     setGhostPage]     = useState(1);
  const [attentionPage, setAttentionPage] = useState(1);
  const [agentsPage,    setAgentsPage]    = useState(1);
  const [sessionPage,   setSessionPage]   = useState(1);

  useEffect(() => {
    Promise.all([
      api.stats(),
      api.attentionQueue(),
      api.ghostQueue(),
      api.trends(),
      api.agents(),
    ]).then(([s, a, g, t, ag]) => {
      setStats(s);
      setAttention(Array.isArray(a) ? a : []);
      setGhost(Array.isArray(g) ? g : []);
      setTrends(t);
      setAgents(Array.isArray(ag) ? ag : []);
      setLoading(false);
    }).catch(() => { setLoading(false); setError(true); });
  }, []);

  // Reset page when tab changes
  const handleTabChange = (t) => {
    setTab(t);
    setGhostPage(1); setAttentionPage(1); setAgentsPage(1); setSessionPage(1);
  };

  const ghostSlice     = ghost.slice((ghostPage - 1) * PAGE_SIZE, ghostPage * PAGE_SIZE);
  const attentionSlice = attention.slice((attentionPage - 1) * PAGE_SIZE, attentionPage * PAGE_SIZE);
  const agentsSlice    = agents.slice((agentsPage - 1) * PAGE_SIZE, agentsPage * PAGE_SIZE);
  const sessions       = (trends?.by_session || []).filter(s => s.trend_label && s.trend_label.trim());
  const sessionSlice   = sessions.slice((sessionPage - 1) * PAGE_SIZE, sessionPage * PAGE_SIZE);

  if (loading) return (
    <div className="flex h-64 items-center justify-center">
      <p className="animate-pulse font-mono text-sm text-zinc-500">Loading dashboard…</p>
    </div>
  );
  if (error) return (
    <div className="flex h-64 items-center justify-center">
      <p className="font-mono text-sm text-red-400">⚠ Could not reach the API. Is the backend running?</p>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <StatCard label="Total calls"        value={stats?.total_calls} />
        <StatCard label="Ghost resolutions"  value={stats?.ghost_calls}
          sub={`${stats?.ghost_rate_pct}% of all calls`} color="red" />
        <StatCard label="True resolution"    value={`${stats?.true_resolution_pct}%`}
          sub="Behavioural" color="green" />
        <StatCard label="Claimed resolved"   value={`${stats?.claimed_resolution_pct}%`}
          sub="Transcript only" color="amber" />
        <StatCard label="Avg duration"       value={stats?.avg_duration_s != null ? `${stats.avg_duration_s.toFixed(0)}s` : "—"} />
        <StatCard label="Avg attention"      value={stats?.avg_attention_score != null ? stats.avg_attention_score.toFixed(0) : "—"}
          color={stats?.avg_attention_score > 50 ? "red" : "zinc"} />
      </div>

      {/* Ghost resolution banner */}
      <div className="rounded-xl border border-red-800 bg-red-950/30 p-5">
        <h2 className="text-base font-semibold text-red-300">
          👻 Ghost Resolution Rate: {stats?.ghost_rate_pct}%
        </h2>
        <p className="mt-1 text-sm text-red-400/80">
          {stats?.ghost_calls} out of {stats?.total_calls} calls were marked resolved but the customer
          called back within 30 minutes. These are the calls that matter most.
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-zinc-800">
        {Object.entries(TAB).map(([k, v]) => (
          <button
            key={k}
            onClick={() => handleTabChange(v)}
            className={`mr-1 rounded-t-md px-4 py-2 font-mono text-xs uppercase tracking-wide transition-colors ${
              tab === v
                ? "border border-b-0 border-zinc-700 bg-zinc-900 text-zinc-100"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {v === TAB.GHOST      ? `👻 Ghost Queue (${ghost.length})` :
             v === TAB.ATTENTION  ? `⚠ Attention Queue (${attention.length})` :
             v === TAB.TRENDS     ? "📈 Trends" : "👤 Agents"}
          </button>
        ))}
      </div>

      {/* Ghost Queue */}
      {tab === TAB.GHOST && (
        <div className="space-y-2">
          <p className="text-xs text-zinc-500">
            Sorted by callback speed — fastest callback = most failed resolution.
          </p>
          {ghost.length === 0 ? (
            <p className="text-zinc-500 text-sm">No ghost resolutions detected yet.</p>
          ) : (
            <>
              {ghostSlice.map((g) => (
                <div
                  key={g.call_id}
                  onClick={() => nav(`/calls/${g.call_id}`)}
                  className="cursor-pointer rounded-lg border border-red-900 bg-zinc-900 p-4 hover:border-red-700 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-sm">{g.customer_name}</span>
                        <span className="text-zinc-500 text-xs">→ {g.agent_name}</span>
                        <span className="rounded-full bg-red-900/60 border border-red-700 px-2 py-0.5 font-mono text-xs text-red-300">
                          called back in {g.ghost_gap_min?.toFixed(1)}m
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-zinc-400 truncate">{g.intent}</p>
                      <p className="mt-1 text-xs text-zinc-500 truncate">{g.summary}</p>
                      {g.next_intent && (
                        <p className="mt-1 text-[11px] text-red-400">
                          → Called back about: {g.next_intent}
                        </p>
                      )}
                    </div>
                    <AttentionScore score={g.attention_score} />
                  </div>
                </div>
              ))}
              <Pagination page={ghostPage} total={ghost.length} pageSize={PAGE_SIZE} onChange={setGhostPage} />
            </>
          )}
        </div>
      )}

      {/* Attention Queue */}
      {tab === TAB.ATTENTION && (
        <div className="space-y-2">
          {attention.length === 0 ? (
            <p className="text-zinc-500 text-sm">No high-attention calls yet.</p>
          ) : (
            <>
              {attentionSlice.map((a) => (
                <div
                  key={a.call_id}
                  onClick={() => nav(`/calls/${a.call_id}`)}
                  className="cursor-pointer rounded-lg border border-zinc-800 bg-zinc-900 p-4 hover:border-zinc-600 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-sm">{a.customer_name}</span>
                        <span className="text-zinc-500 text-xs">→ {a.agent_name}</span>
                        <MoodBadge mood={a.mood_start} shift={!!a.mood_shift} direction={a.mood_shift_direction} />
                        {a.ghost_resolved ? (
                          <span className="ghost-badge rounded-full px-2 py-0.5 text-xs">👻 Ghost</span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-xs text-zinc-400 truncate">{a.intent}</p>
                      <p className="mt-0.5 text-xs text-zinc-500">{a.attention_reason}</p>
                    </div>
                    <AttentionScore score={a.attention_score} />
                  </div>
                </div>
              ))}
              <Pagination page={attentionPage} total={attention.length} pageSize={PAGE_SIZE} onChange={setAttentionPage} />
            </>
          )}
        </div>
      )}

      {/* Trends */}
      {tab === TAB.TRENDS && trends && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <h3 className="mb-3 font-mono text-xs uppercase tracking-wide text-zinc-500">Issue clusters</h3>
            {(trends.clusters || []).length === 0 ? (
              <p className="text-sm text-zinc-500">No clusters yet — run the clustering pipeline to group issues.</p>
            ) : (
              <div className="space-y-2">
                {(trends.clusters || []).map((c) => (
                  <div key={c.cluster_id} className="rounded-lg border border-zinc-800 bg-zinc-900 p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-sm">{c.label}</span>
                      <span className="font-mono text-xs text-zinc-500">{c.call_count} calls</span>
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-xs">
                      {c.ghost_rate != null && (
                        <span className="text-red-400">{(c.ghost_rate * 100).toFixed(0)}% ghost</span>
                      )}
                      {c.avg_attention != null && (
                        <span className="text-zinc-500">avg attention: {c.avg_attention?.toFixed(0)}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div>
            <h3 className="mb-3 font-mono text-xs uppercase tracking-wide text-zinc-500">By session</h3>
            <div className="space-y-1">
              {sessionSlice.map((s, i) => (
                <div key={`${s.session}-${s.trend_label}-${i}`} className="flex items-center justify-between rounded border border-zinc-800 px-3 py-1.5">
                  <div className="min-w-0 flex-1">
                    <span className="text-xs text-zinc-400">{s.session}: </span>
                    <span className="text-xs text-zinc-200">{s.trend_label}</span>
                  </div>
                  <span className="ml-2 font-mono text-xs text-zinc-500">{s.count}</span>
                </div>
              ))}
            </div>
            <Pagination page={sessionPage} total={sessions.length} pageSize={PAGE_SIZE} onChange={setSessionPage} />
          </div>
        </div>
      )}

      {/* Agents */}
      {tab === TAB.AGENTS && (
        <div className="space-y-3">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left font-mono text-xs uppercase tracking-wide text-zinc-500">
                  <th className="pb-2 pr-4">Agent</th>
                  <th className="pb-2 pr-4">Calls</th>
                  <th className="pb-2 pr-4">Avg duration</th>
                  <th className="pb-2 pr-4 text-red-400">Ghost rate ↓</th>
                  <th className="pb-2 pr-4 text-green-400">True resolved</th>
                  <th className="pb-2 pr-4">Claimed</th>
                  <th className="pb-2">Avg attention</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {agentsSlice.map((a) => (
                  <tr key={a.agent_name} className="hover:bg-zinc-900 transition-colors">
                    <td className="py-2.5 pr-4 font-medium">{a.agent_name}</td>
                    <td className="py-2.5 pr-4 font-mono text-zinc-400">{a.total}</td>
                    <td className="py-2.5 pr-4 font-mono text-zinc-400">{a.avg_duration_s?.toFixed(0)}s</td>
                    <td className="py-2.5 pr-4">
                      <span className={`font-mono font-semibold ${
                        a.ghost_rate > 0.37 ? "text-red-400" :
                        a.ghost_rate > 0.33 ? "text-orange-400" : "text-green-400"
                      }`}>
                        {(a.ghost_rate * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-green-400">{(a.true_resolution_rate * 100).toFixed(1)}%</td>
                    <td className="py-2.5 pr-4 font-mono text-zinc-400">{(a.claimed_resolution_rate * 100).toFixed(1)}%</td>
                    <td className="py-2.5 font-mono text-zinc-400">{a.avg_attention_score?.toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={agentsPage} total={agents.length} pageSize={PAGE_SIZE} onChange={setAgentsPage} />
          <p className="text-xs text-zinc-600">
            Ghost rate = % of calls where customer called back within 30 min despite agent marking resolved.
            True resolved = behavioural evidence (no callback).
          </p>
        </div>
      )}
    </div>
  );
}
