import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchCompare, fetchGrid } from "../api.js";
import Outcome from "../components/Outcome.jsx";

const MODEL_NAMES = { m0: "M0 plain prompt", m1: "M1 retrieval", m2: "M2 spec-first", m3: "M3", m4: "M4" };
const WHAT = {
  m0: "One prompt; ships if its own tests pass.",
  m1: "Retrieved examples + generator; ships if tests, fuzzing, policy and contract checks pass.",
  m2: "Writes and checks a spec first; app from the frozen spec; tests generated from the spec.",
};

function FileView({ name, text }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-slate-800 rounded">
      <button type="button" onClick={() => setOpen(!open)} className="w-full text-left px-2 py-1 text-xs text-slate-300 hover:bg-slate-900">
        {open ? "▾" : "▸"} {name} <span className="text-slate-500">({text.split("\n").length} lines)</span>
      </button>
      {open && <pre className="max-h-96 overflow-auto p-2 text-xs bg-slate-950 whitespace-pre">{text}</pre>}
    </div>
  );
}

export default function Compare() {
  const [params, setParams] = useSearchParams();
  const grid = params.get("grid") || "demo1";
  const task = params.get("task") || "";
  const repeat = Number(params.get("repeat") || 1);
  const [tasks, setTasks] = useState([]);
  const [repeats, setRepeats] = useState([1]);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchGrid(grid)
      .then((g) => {
        const ts = [...new Set(g.runs.map((r) => r.task))].sort();
        setTasks(ts);
        setRepeats([...new Set(g.runs.map((r) => r.repeat))].sort());
        if (!task && ts.length) setParams({ grid, task: ts[0], repeat: "1" });
      })
      .catch((e) => setError(String(e.message || e)));
  }, [grid]);
  useEffect(() => {
    if (!task) return;
    setData(null);
    setError("");
    fetchCompare(grid, task, repeat).then(setData).catch((e) => setError(String(e.message || e)));
  }, [grid, task, repeat]);

  const set = (k, v) => setParams({ grid, task, repeat: String(repeat), [k]: String(v) });

  return (
    <div className="max-w-7xl mx-auto p-4 space-y-4">
      <Link to={`/results?grid=${grid}`} className="text-xs text-indigo-400 hover:underline">← Results</Link>
      <div className="flex flex-wrap items-end gap-3">
        <h2 className="text-xl font-bold mr-auto">Compare models on one task</h2>
        <label className="text-sm">Task{" "}
          <select className="ml-1 bg-slate-900 border border-slate-700 rounded p-1" value={task} onChange={(e) => set("task", e.target.value)}>
            {tasks.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="text-sm">Repeat{" "}
          <select className="ml-1 bg-slate-900 border border-slate-700 rounded p-1" value={repeat} onChange={(e) => set("repeat", e.target.value)}>
            {repeats.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
      </div>
      {error && <p className="text-red-400 text-sm">{error}</p>}
      {data && (
        <div className="grid gap-3 md:grid-cols-3">
          {Object.entries(data.models).map(([m, run]) => (
            <div key={m} className="rounded border border-slate-800 p-3 space-y-2 bg-slate-900/40">
              <h3 className="font-semibold">{MODEL_NAMES[m] || m}</h3>
              {WHAT[m] && <p className="text-xs text-slate-400">{WHAT[m]}</p>}
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span>Model said <b>{run.decision}</b></span>
                <Outcome run={run} />
              </div>
              {run.failed_verifiers?.length > 0 && (
                <p className="text-xs text-slate-300">Its own gate failed: {run.failed_verifiers.join(", ")}</p>
              )}
              {m === "m2" && run.spec_source && (
                <p className="text-xs text-slate-300">
                  Spec: {run.spec_source === "llm" ? "written by the model and checked" : "fell back to the interface-only spec"}
                  {run.spec_tests?.cases != null && ` · ${run.spec_tests.cases} spec tests`}
                </p>
              )}
              <p className="text-xs text-slate-400">
                Own tests catch: {run.violation_recall == null ? "-" : `${Math.round(run.violation_recall * 100)}% of benchmark bugs`}
                {run.own_mutation_score != null && ` · ${Math.round(run.own_mutation_score * 100)}% of own-app mutants`}
              </p>
              <div>
                <p className="text-xs font-semibold text-slate-300 mb-1">
                  Hidden checks failed ({run.failed_checks.length})
                </p>
                {run.failed_checks.length === 0 ? (
                  <p className="text-xs text-emerald-400">None: this app passes every hidden check.</p>
                ) : (
                  <ul className="text-xs space-y-1 max-h-48 overflow-auto">
                    {run.failed_checks.map((c) => (
                      <li key={c.id} title={c.detail}>
                        <span className={c.kind === "safety" ? "text-red-300" : "text-amber-200"}>[{c.kind}]</span>{" "}
                        {c.id.replace(/^test_/, "").replace(/_/g, " ")}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="space-y-1">
                {Object.entries(run.files).map(([f, text]) => <FileView key={f} name={f} text={text} />)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
