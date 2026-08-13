import { useEffect, useState } from "react";
import { getHealth, getReadiness } from "./services/api";

/**
 * Application shell for the Agent Action Firewall operational security
 * dashboard (PRODUCT_SPEC.md §15). Day 1 only proves the frontend can talk
 * to the backend's health/readiness endpoints; the Dashboard/Agent/Task/
 * Policy/Decision/Audit pages described in the product spec are built once
 * their backing APIs exist (Day 3+).
 */
function App() {
  const [backendStatus, setBackendStatus] = useState<"checking" | "ok" | "error">(
    "checking"
  );
  const [readiness, setReadiness] = useState<"checking" | "ready" | "not_ready">(
    "checking"
  );

  useEffect(() => {
    getHealth()
      .then(() => setBackendStatus("ok"))
      .catch(() => setBackendStatus("error"));

    getReadiness()
      .then(({ ok }) => setReadiness(ok ? "ready" : "not_ready"))
      .catch(() => setReadiness("not_ready"));
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4">
        <h1 className="text-xl font-semibold tracking-tight">
          Agent Action Firewall
        </h1>
        <p className="text-sm text-slate-400">
          Task-scoped authorization gateway — security dashboard (POC)
        </p>
      </header>

      <main className="p-6">
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 max-w-md space-y-4">
          <div>
            <h2 className="text-sm font-medium text-slate-300 mb-2">
              Backend connectivity
            </h2>
            <StatusBadge status={backendStatus} />
          </div>
          <div>
            <h2 className="text-sm font-medium text-slate-300 mb-2">
              Dependencies (DB + Redis)
            </h2>
            <ReadinessBadge status={readiness} />
          </div>
        </div>
      </main>
    </div>
  );
}

function StatusBadge({ status }: { status: "checking" | "ok" | "error" }) {
  const styles = {
    checking: "bg-slate-700 text-slate-200",
    ok: "bg-emerald-900 text-emerald-300",
    error: "bg-red-900 text-red-300",
  } as const;
  const label = {
    checking: "Checking...",
    ok: "Connected",
    error: "Unreachable",
  } as const;

  return (
    <span className={`inline-block rounded px-2 py-1 text-xs font-medium ${styles[status]}`}>
      {label[status]}
    </span>
  );
}

function ReadinessBadge({ status }: { status: "checking" | "ready" | "not_ready" }) {
  const styles = {
    checking: "bg-slate-700 text-slate-200",
    ready: "bg-emerald-900 text-emerald-300",
    not_ready: "bg-red-900 text-red-300",
  } as const;
  const label = {
    checking: "Checking...",
    ready: "Ready",
    not_ready: "Not Ready",
  } as const;

  return (
    <span className={`inline-block rounded px-2 py-1 text-xs font-medium ${styles[status]}`}>
      {label[status]}
    </span>
  );
}

export default App;
