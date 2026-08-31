const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  // Core
  stats:               ()            => req("/dashboard/stats"),
  attentionQueue:      (limit=50)    => req(`/dashboard/attention?limit=${limit}`),
  ghostQueue:          (limit=50, unresolvedOnly=true) =>
                         req(`/dashboard/ghost-queue?limit=${limit}&unresolved_only=${unresolvedOnly}`),
  trends:              ()            => req("/dashboard/trends"),
  agents:              ()            => req("/dashboard/agents"),
  trajectories:        (limit=20)    => req(`/dashboard/customer-trajectories?limit=${limit}`),
  customers:           (search="",sort="ghost_rate") =>
                         req(`/customers?search=${encodeURIComponent(search)}&sort_by=${sort}`),
  customerCalls:       (name)        => req(`/customers/${encodeURIComponent(name)}/calls`),
  call:                (id)          => req(`/calls/${id}`),
  audioUrl:            (id)          => `${BASE}/audio/${id}`,

  // Compliance (CortexV improvement)
  callCompliance:      (id)          => req(`/calls/${id}/compliance`),
  evaluateCompliance:  (id)          => req(`/calls/${id}/compliance/evaluate`, { method: "POST" }),
  complianceRules:     ()            => req("/compliance/rules"),
  complianceDashboard: ()            => req("/dashboard/compliance"),
  createRule:          (rule)        => req("/compliance/rules", {
                           method: "POST",
                           body: JSON.stringify(rule),
                         }),

  // Follow-up suggestions (CortexV improvement)
  callSuggestions:     (id)          => req(`/calls/${id}/suggestions`),

  // Sentiment dashboard (CortexV improvement)
  sentimentDashboard:  ()            => req("/dashboard/sentiment"),

  // Customer Perception Dashboard
  issueFrequency:      (from="", to="", limit=15) => req(`/dashboard/issues?limit=${limit}${from ? `&from_date=${from}` : ""}${to ? `&to_date=${to}` : ""}`),
  issueDetail:         (intent)                   => req(`/dashboard/issues/${encodeURIComponent(intent)}/detail`),
  satisfaction:        (from="", to="")           => req(`/dashboard/satisfaction?${from ? `from_date=${from}&` : ""}${to ? `to_date=${to}` : ""}`),
  rudeAgents:          (minCalls=3)              => req(`/dashboard/rude-agents?min_calls=${minCalls}`),
  spamCallers:         (limit=50)                => req(`/dashboard/spam-callers?limit=${limit}`),
  agentPerformance:    ()                        => req("/dashboard/performance"),
};
