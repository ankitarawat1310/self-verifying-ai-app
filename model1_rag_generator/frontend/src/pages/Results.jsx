import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { chartUrl, fetchGrid, fetchGrids } from "../api.js";
import Outcome, { OUTCOMES, outcomeOf } from "../components/Outcome.jsx";

const MODEL_NAMES = { m0: "M0 plain prompt", m1: "M1 retrieval", m2: "M2 spec-first", m3: "M3", m4: "M4" };
const METRICS = [
  ["functional_pass", "Passes every hidden check", true],
  ["false_assurance_of_accepted", "Broken among shipped apps (false assurance)", false],
  ["shipped_broken_per_run", "Runs that shipped a broken app", false],
  ["false_rejection_of_rejected", "Correct among rejected apps", false],
  ["hidden_check_rate", "Hidden checks passed", true],
  ["benchmark_bug_recall", "Seeded bugs caught by own tests", true],
  ["own_mutation_score", "Own-app mutants caught by own tests", true],
];

const pct = (v) => (v == null ? "-" : `${Math.round(v * 100)}%`);

export default function Results() {
  const [params, setParams] = useSearchParams();
  const [grids, setGrids] = useState([]);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const name = params.get("grid") || grids.find((g) => g.name === "demo1")?.name || grids[0]?.name;

  useEffect(() => {
    fetchGrids().then(setGrids).catch((e) => setError(String(e.message || e)));
  }, []);
  useEffect(() => {
    if (!name) return;
    setData(null);
    fetchGrid(name).then(setData).catch((e) => setError(String(e.message || e)));
  }, [name]);

  const models = useMemo(() => [...new Set((data?.runs || []).map((r) => r.model))].sort(), [data]);
  const tasks = useMemo(() => [...new Set((data?.runs || []).map((r) => r.task))].sort(), [data]);
  const repeats = useMemo(() => [...new Set((data?.runs || []).map((r) => r.repeat))].sort(), [data]);
  const byCell = useMemo(() => {
    const m = {};
    (data?.runs || []).forEach((r) => (m[`${r.model}|${r.task}|${r.repeat}`] = r));
    return m;
  }, [data]);
  const stats = data?.analysis?.stats;

  return (
    <div className="max-w-6xl mx-auto p-4 space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <h2 className="text-xl font-bold">Experiment results</h2>
          <p className="text-sm text-slate-400">
            Each run: the model's own ACCEPT/REJECT, scored against hidden checks it never saw.
          </p>
        </div>
        <label className="ml-auto text-sm">
          Run set{" "}
          <select
            className="ml-1 bg-slate-900 border border-slate-700 rounded p-1"
            value={name || ""}
            onChange={(e) => setParams({ grid: e.target.value })}
          >
            {grids.map((g) => (
              <option key={g.name} value={g.name}>
                {g.name} ({g.runs} runs, {g.split || "custom"})
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p className="text-red-400 text-sm">{error}</p>}
      {!grids.length && !error && <p className="text-slate-400 text-sm">No results yet. Run scripts/run_grid.py first.</p>}
      {data && (
        <>
          <p className="text-xs text-slate-500">
            Model: {data.config?.llm?.model || "?"} · {tasks.length} tasks × {repeats.length} repeats ·{" "}
            {data.runs.length} runs
          </p>

          <section>
            <h3 className="font-semibold mb-2">Headline metrics {stats && <span className="text-xs text-slate-400">(95% intervals, bootstrap over tasks)</span>}</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-800">
                <thead>
                  <tr className="bg-slate-900">
                    <th className="p-2 text-left">Metric</th>
                    {models.map((m) => (
                      <th key={m} className="p-2 text-right">{MODEL_NAMES[m] || m}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {stats
                    ? METRICS.map(([key, label, higher]) => (
                        <tr key={key} className="border-t border-slate-800">
                          <td className="p-2">
                            {label} <span className="text-xs text-slate-500">({higher ? "higher" : "lower"} is better)</span>
                          </td>
                          {models.map((m) => {
                            const s = stats[m]?.[key];
                            return (
                              <td key={m} className="p-2 text-right tabular-nums">
                                {pct(s?.value)}{" "}
                                {s?.ci_low != null && (
                                  <span className="text-xs text-slate-500">[{pct(s.ci_low)}, {pct(s.ci_high)}]</span>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))
                    : Object.entries(data.summary || {}).length > 0 && (
                        <tr>
                          <td colSpan={models.length + 1} className="p-2 text-slate-400">
                            Run scripts/analyze_grid.py for intervals; raw summary.json is available.
                          </td>
                        </tr>
                      )}
                </tbody>
              </table>
            </div>
          </section>

          {data.charts.length > 0 && (
            <section className="grid md:grid-cols-2 gap-3">
              {data.charts.map((c) => (
                <a key={c} href={chartUrl(data.name, c)} target="_blank" rel="noreferrer" title="Open full size">
                  <img src={chartUrl(data.name, c)} alt={c.replace(/_/g, " ").replace(".png", "")}
                    className="w-full rounded border border-slate-800 bg-white" />
                </a>
              ))}
            </section>
          )}

          <section>
            <h3 className="font-semibold mb-1">Every run</h3>
            <div className="flex flex-wrap gap-2 mb-2 text-xs">
              {Object.entries(OUTCOMES).map(([k, o]) => (
                <span key={k} className={`rounded px-2 py-0.5 ${o.cls}`}>{o.label}</span>
              ))}
              <span className="text-slate-400">· number = hidden checks passed · click a task to compare the models</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-800">
                <thead>
                  <tr className="bg-slate-900">
                    <th className="p-2 text-left">Task</th>
                    {models.map((m) => (
                      <th key={m} className="p-2 text-left">{MODEL_NAMES[m] || m}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((t) => (
                    <tr key={t} className="border-t border-slate-800 align-top">
                      <td className="p-2">
                        <Link className="text-indigo-300 hover:underline" to={`/compare?grid=${data.name}&task=${t}&repeat=1`}>
                          {t}
                        </Link>
                      </td>
                      {models.map((m) => (
                        <td key={m} className="p-2">
                          <div className="flex flex-wrap gap-1">
                            {repeats.map((r) => {
                              const run = byCell[`${m}|${t}|${r}`];
                              return (
                                <Link key={r} to={`/compare?grid=${data.name}&task=${t}&repeat=${r}`}
                                  title={`repeat ${r}: ${run ? OUTCOMES[outcomeOf(run)].label : "missing"}`}>
                                  <Outcome run={run} compact />
                                </Link>
                              );
                            })}
                          </div>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
