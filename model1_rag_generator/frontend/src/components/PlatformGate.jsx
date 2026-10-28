import { useEffect, useState } from "react";

/**
 * Ensures the Vite dev server is proxying to SVAGA 3.0 API — not SVAGA 2.0 or a generated app.
 */
export default function PlatformGate({ children }) {
  const [state, setState] = useState({ loading: true, ok: false, detail: "" });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/v1/health");
        if (!res.ok) throw new Error(`API HTTP ${res.status}`);
        const data = await res.json();
        if (data.platform !== "svaga_3.0") {
          throw new Error(
            "Connected API is not SVAGA 3.0 (wrong backend or another app on this port)."
          );
        }
        if (!cancelled) setState({ loading: false, ok: true, detail: "" });
      } catch (e) {
        if (!cancelled) {
          setState({
            loading: false,
            ok: false,
            detail: String(e.message || e),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-400">
        Connecting to SVAGA 3.0 API…
      </div>
    );
  }

  if (!state.ok) {
    return (
      <div className="min-h-screen p-8 max-w-xl mx-auto space-y-4">
        <h1 className="text-2xl font-bold text-red-400">Wrong app or API</h1>
        <p className="text-slate-300">
          This page must be the <strong>SVAGA 3.0 console</strong> with the 3.0 backend on port{" "}
          <strong>8003</strong> (not 8000/8002 — those are often SVAGA 2.0 or generated apps).
        </p>
        <p className="text-sm text-slate-400">{state.detail}</p>
        <pre className="text-xs bg-slate-900 p-4 rounded overflow-x-auto whitespace-pre-wrap">
          {`# Terminal 1 — SVAGA 3.0 API
cd "SVAGA 3.0"
$env:PYTHONPATH="."; $env:SVAGA_SCRIPTED_LLM="1"
python -m uvicorn svaga_platform.app.main:app --port 8003

# Terminal 2 — SVAGA 3.0 console (port 5303)
cd model1_rag_generator\\frontend
$env:VITE_PROXY_TARGET="http://127.0.0.1:8003"
npm run dev`}
        </pre>
        <p className="text-sm">
          Then open <strong>http://localhost:5303</strong> (not 5173/5174).
        </p>
      </div>
    );
  }

  return children;
}
