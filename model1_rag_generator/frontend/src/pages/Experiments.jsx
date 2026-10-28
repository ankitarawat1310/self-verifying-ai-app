import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchBenchmarks, startExperiment } from "../api.js";

export default function Experiments() {
  const [workflowId, setWorkflowId] = useState("url_shortener");
  const [pipelines, setPipelines] = useState(["m1", "m2", "m3", "m4"]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [benchmarks, setBenchmarks] = useState([]);

  useEffect(() => {
    fetchBenchmarks().then(setBenchmarks).catch(() => {});
  }, []);

  function togglePipeline(p) {
    setPipelines((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  }

  async function run() {
    setLoading(true);
    try {
      const data = await startExperiment({ workflow_ids: [workflowId], pipelines });
      setResult(data);
    } catch (e) {
      setResult({ error: String(e.message || e) });
    } finally {
      setLoading(false);
    }
  }

  const metrics = result?.metrics;
  const rows = metrics?.rows || [];

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-4">
      <Link to="/" className="text-xs text-indigo-400 hover:underline">
        ← Home
      </Link>
      <h2 className="text-xl font-bold">Pipeline comparison (M1–M4)</h2>
      <p className="text-sm text-slate-400">
        Same benchmark and budget profile — functional pass, verification time, tokens.
      </p>
      <label className="block text-sm">
        Workflow
        <input
          className="mt-1 w-full bg-slate-900 border border-slate-700 rounded p-2"
          value={workflowId}
          onChange={(e) => setWorkflowId(e.target.value)}
          list="wf-list"
        />
        <datalist id="wf-list">
          {benchmarks.map((b) => (
            <option key={b.workflow_id} value={b.workflow_id} />
          ))}
        </datalist>
      </label>
      <div className="flex gap-2 flex-wrap">
        {["m0", "m1", "m2", "m3", "m4"].map((p) => (
          <label key={p} className="flex items-center gap-1 text-sm">
            <input type="checkbox" checked={pipelines.includes(p)} onChange={() => togglePipeline(p)} />
            {p.toUpperCase()}
          </label>
        ))}
      </div>
      <button
        type="button"
        disabled={loading || pipelines.length === 0}
        onClick={run}
        className="rounded bg-indigo-600 px-4 py-2 disabled:opacity-50"
      >
        {loading ? "Running…" : "Run experiment"}
      </button>
      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
          <div className="bg-slate-900 p-3 rounded">Pass rate: {(metrics.functional_pass_rate * 100).toFixed(0)}%</div>
          <div className="bg-slate-900 p-3 rounded">Verify time: {metrics.verification_time_seconds?.toFixed(1)}s</div>
          <div className="bg-slate-900 p-3 rounded">Tokens: {metrics.llm_tokens}</div>
          <div className="bg-slate-900 p-3 rounded">Repair ok: {(metrics.repair_success * 100).toFixed(0)}%</div>
        </div>
      )}
      {result?.run_id && (
        <p className="text-xs text-slate-400">Results saved under results/{result.run_id}/</p>
      )}
      {rows.length > 0 && (
        <table className="w-full text-sm border border-slate-800">
          <thead>
            <tr className="bg-slate-900">
              <th className="p-2 text-left">Pipeline</th>
              <th className="p-2 text-left">Decision</th>
              <th className="p-2 text-right">Verify (s)</th>
              <th className="p-2 text-right">Tokens</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-slate-800">
                <td className="p-2">{r.pipeline}</td>
                <td className="p-2">{r.decision}</td>
                <td className="p-2 text-right">{r.verification_seconds?.toFixed?.(2) ?? r.verification_seconds}</td>
                <td className="p-2 text-right">{r.tokens}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {result?.error && <p className="text-red-400">{result.error}</p>}
    </div>
  );
}
