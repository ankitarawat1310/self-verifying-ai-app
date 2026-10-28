import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PromptInput from "../components/PromptInput.jsx";
import { fetchBenchmarks, fetchConfig, runWorkflow } from "../api.js";

export default function CreateRun() {
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState(
    "Build a URL shortener API with POST /shorten and GET /r/{code}."
  );
  const [workflowId, setWorkflowId] = useState("");
  const [pipeline, setPipeline] = useState("m1");
  const [benchmarks, setBenchmarks] = useState([]);
  const [llm, setLlm] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchBenchmarks().then(setBenchmarks).catch(() => {});
    fetchConfig().then((c) => setLlm(c.llm)).catch(() => {});
  }, []);

  useEffect(() => {
    if (workflowId) {
      const b = benchmarks.find((x) => x.workflow_id === workflowId);
      if (b && !prompt) setPrompt(b.name);
    }
  }, [workflowId, benchmarks]);

  async function onSubmit() {
    setLoading(true);
    setError("");
    try {
      const body = {
        pipeline,
        natural_language: prompt,
        workflow_id: workflowId || null,
      };
      const result = await runWorkflow(body);
      navigate(`/runs/${result.run_id}`, { state: { result } });
    } catch (e) {
      const msg = String(e.message || e);
      if (msg === "Failed to fetch" || msg.includes("NetworkError")) {
        setError(
          "Failed to fetch — is the SVAGA 3.0 API running on port 8003? Restart the UI after: " +
            "python -m uvicorn svaga_platform.app.main:app --port 8003 (from SVAGA 3.0 folder). " +
            "Do not set VITE_API_BASE in dev; use the Vite proxy."
        );
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto p-4 space-y-4">
      <h2 className="text-xl font-bold">Create workflow run</h2>
      {llm && (
        <p className="text-xs text-slate-400">
          LLM: {llm.provider} / {llm.model}
        </p>
      )}
      <label className="block text-sm">
        Pipeline
        <select
          className="mt-1 w-full bg-slate-900 border border-slate-700 rounded p-2"
          value={pipeline}
          onChange={(e) => setPipeline(e.target.value)}
        >
          {["m0", "m1", "m2", "m3", "m4"].map((p) => (
            <option key={p} value={p}>
              {p.toUpperCase()}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        Benchmark (optional)
        <select
          className="mt-1 w-full bg-slate-900 border border-slate-700 rounded p-2"
          value={workflowId}
          onChange={(e) => {
            const id = e.target.value;
            setWorkflowId(id);
            const b = benchmarks.find((x) => x.workflow_id === id);
            if (b?.natural_language_requirement) {
              setPrompt(b.natural_language_requirement);
            }
          }}
        >
          <option value="">Free-form natural language</option>
          {benchmarks.map((b) => (
            <option key={b.workflow_id} value={b.workflow_id}>
              {b.name} ({b.workflow_id})
            </option>
          ))}
        </select>
      </label>
      <PromptInput value={prompt} onChange={setPrompt} onSubmit={onSubmit} loading={loading} label={`Generate with ${pipeline.toUpperCase()}`} />
      {error && <p className="text-red-400 text-sm">{error}</p>}
    </div>
  );
}
