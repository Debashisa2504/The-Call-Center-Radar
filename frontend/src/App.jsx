import { Routes, Route, NavLink } from "react-router-dom";
import Dashboard          from "./pages/Dashboard.jsx";
import Customers          from "./pages/Customers.jsx";
import CustomerDetail     from "./pages/CustomerDetail.jsx";
import CallDetail         from "./pages/CallDetail.jsx";
import CustomerPerception from "./pages/CustomerPerception.jsx";

const NAV = [
  { to: "/",           label: "Dashboard" },
  { to: "/customers",  label: "Customers" },
  { to: "/perception", label: "Perception" },
];

export default function App() {
  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Top bar */}
      <header className="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <span className="text-lg font-semibold tracking-tight">📡 Call Radar</span>
            <span className="hidden font-mono text-xs text-zinc-500 sm:block">
              Ghost Resolution Intelligence
            </span>
          </div>
          <nav className="flex gap-1">
            {NAV.map(n => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 font-mono text-xs transition-colors ${
                    isActive
                      ? "bg-zinc-800 text-zinc-100"
                      : "text-zinc-500 hover:text-zinc-200"
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-6">
        <Routes>
          <Route path="/"                          element={<Dashboard />} />
          <Route path="/customers"                 element={<Customers />} />
          <Route path="/customers/:name"           element={<CustomerDetail />} />
          <Route path="/calls/:callId"             element={<CallDetail />} />
          <Route path="/perception"               element={<CustomerPerception />} />
          <Route path="*"                          element={<p className="text-zinc-500 p-8">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
