import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import Pagination from "../components/Pagination.jsx";

const PAGE_SIZE = 15;

export default function Customers() {
  const nav = useNavigate();
  const [customers, setCustomers] = useState([]);
  const [search, setSearch]       = useState("");
  const [sort, setSort]           = useState("ghost_rate");
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [page, setPage]           = useState(1);
  const debounceRef = useRef(null);

  useEffect(() => {
    // Debounce search — wait 300ms after last keystroke before fetching
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setLoading(true);
      setError(null);
      api.customers(search, sort)
        .then(c => { setCustomers(Array.isArray(c) ? c : []); setPage(1); setLoading(false); })
        .catch(() => { setError("Failed to load customers."); setLoading(false); });
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [search, sort]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder="Search customers…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-blue-600 focus:outline-none"
        />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:outline-none"
        >
          <option value="ghost_rate">Sort: Ghost rate ↓</option>
          <option value="total_calls">Sort: Call volume ↓</option>
          <option value="avg_attention">Sort: Attention ↓</option>
          <option value="name">Sort: Name A–Z</option>
        </select>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {loading ? (
        <p className="animate-pulse font-mono text-sm text-zinc-500">Loading customers…</p>
      ) : customers.length === 0 ? (
        <p className="text-zinc-500 text-sm">No customers found.</p>
      ) : (
        <div className="space-y-3">
        <p className="text-xs leading-relaxed text-zinc-500">
          <b className="text-zinc-400">Ghost rate</b>: % of this customer's calls where the agent marked the
          issue resolved but the customer called back about the same thing.{" "}
          <b className="text-zinc-400">True resolved</b>: % confirmed resolved by what actually happened on
          the call, not just the agent's claim.{" "}
          <b className="text-zinc-400">Avg attention</b>: 0–100 composite score — higher means more of this
          customer's calls need a manager's review.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-left font-mono text-xs uppercase tracking-wide text-zinc-500">
                <th className="pb-2 pr-4">Customer</th>
                <th className="pb-2 pr-4">Calls</th>
                <th className="pb-2 pr-4 text-red-400">Ghost rate</th>
                <th className="pb-2 pr-4 text-green-400">True resolved</th>
                <th className="pb-2 pr-4">Avg attention</th>
                <th className="pb-2">Issues</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {customers.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((c) => (
                <tr
                  key={c.customer_name}
                  onClick={() => nav(`/customers/${encodeURIComponent(c.customer_name)}`)}
                  className="cursor-pointer hover:bg-zinc-900 transition-colors"
                >
                  <td className="py-2.5 pr-4 font-medium">{c.customer_name}</td>
                  <td className="py-2.5 pr-4 font-mono text-zinc-400">{c.total_calls}</td>
                  <td className="py-2.5 pr-4">
                    <span className={`font-mono font-semibold ${
                      c.ghost_rate_pct > 40 ? "text-red-400" :
                      c.ghost_rate_pct > 25 ? "text-orange-400" : "text-green-400"
                    }`}>
                      {c.ghost_rate_pct}%
                    </span>
                  </td>
                  <td className="py-2.5 pr-4 font-mono text-green-400">{c.true_resolution_pct}%</td>
                  <td className="py-2.5 pr-4 font-mono text-zinc-400">{c.avg_attention?.toFixed(0)}</td>
                  <td className="py-2.5 text-xs text-zinc-500 truncate max-w-[180px]">
                    {typeof c.issues === "string"
                      ? c.issues.split(",").slice(0, 2).join(", ")
                      : Array.isArray(c.issues)
                        ? c.issues.slice(0, 2).join(", ")
                        : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={page} total={customers.length} pageSize={PAGE_SIZE} onChange={setPage} />
        </div>
      )}
    </div>
  );
}
