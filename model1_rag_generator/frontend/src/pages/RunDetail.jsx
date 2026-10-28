import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import CodeEditor from "../components/CodeEditor.jsx";
import LogsViewer from "../components/LogsViewer.jsx";
import ReleaseBadge from "../components/ReleaseBadge.jsx";
import RunStepper from "../components/RunStepper.jsx";
import VerifierTable from "../components/VerifierTable.jsx";
import { downloadUrl, fetchRun, startPreview, stopPreview } from "../api.js";

export default function RunDetail() {
  const { runId } = useParams();
  const location = useLocation();
  const [run, setRun] = useState(location.state?.result || null);
  const [tab, setTab] = useState("app");
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState("");

  useEffect(() => {
    if (!run && runId) {
      fetchRun(runId).then(setRun).catch(() => {});
    }
  }, [runId, run]);

  if (!run) {
    return <p className="p-4">Loading run…</p>;
  }

  const artifacts = run.artifacts || {};
  const gate = run.release_gate || { decision: run.decision, reasons: run.metadata?.gate_reasons || [] };
  const verifiers = run.verification?.verifiers || [];
  const chunkIds = run.metadata?.retrieval?.chunk_ids || run.provenance?.retrieval?.chunk_ids;
  const context =
    run.provenance?.retrieved_context ||
    run.metadata?.retrieved_context ||
    (chunkIds?.length ? `Retrieved chunks (text not saved for this older run):\n${chunkIds.map((c) => `- ${c}`).join("\n")}` : "") ||
    (run.pipeline === "m0" ? "(M0 uses no retrieval)" : "");
  const pytest = verifiers.find((v) => v.name === "pytest_sandbox");
  const logs = [pytest?.details?.stdout, pytest?.details?.stderr].filter(Boolean).join("\n");
  const stepIndex = gate.decision ? 5 : 3;

  async function onPreviewStart() {
    setPreviewError("");
    try {
      const p = await startPreview(run.run_id);
      setPreview(p);
    } catch (e) {
      setPreviewError(String(e.message || e));
    }
  }

  async function onPreviewStop() {
    await stopPreview(run.run_id);
    setPreview(null);
  }

  return (
    <div className="p-4 max-w-6xl mx-auto space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link to="/" className="text-xs text-indigo-400 hover:underline">
            ← Home
          </Link>
          <h2 className="text-xl font-bold mt-1">
            Run {run.run_id?.slice(0, 8)} · {run.pipeline?.toUpperCase()}
          </h2>
          <p className="text-sm text-slate-400">{run.workflow_id}</p>
        </div>
        <ReleaseBadge decision={gate.decision} reasons={gate.reasons} />
      </div>

      <RunStepper activeIndex={stepIndex} />

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="space-y-3">
          <h3 className="text-sm font-semibold">Retrieved context</h3>
          <pre className="text-xs max-h-32 overflow-auto bg-slate-900 border border-slate-800 rounded p-2">
            {context || "—"}
          </pre>
          <h3 className="text-sm font-semibold">Verification</h3>
          <VerifierTable verifiers={verifiers} />
          {run.counterexamples?.length > 0 && (
            <pre className="text-xs text-red-300 bg-slate-900 p-2 rounded overflow-auto">
              {JSON.stringify(run.counterexamples, null, 2)}
            </pre>
          )}
        </div>
        <div className="flex flex-col min-h-[60vh]">
          <div className="flex flex-wrap gap-2 mb-2">
            {[
              ["app", "app.py"],
              ["tests", "test_app.py"],
              ["spec", "workflow_spec.json"],
              ["policy", "policy.json"],
              ["logs", "Logs"],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={`px-3 py-1 rounded text-sm ${tab === key ? "bg-slate-700" : "bg-slate-800"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex-1 border border-slate-800 rounded-lg overflow-hidden min-h-[400px]">
            {tab === "app" && <CodeEditor value={artifacts["app.py"] || ""} readOnly />}
            {tab === "tests" && <CodeEditor value={artifacts["test_app.py"] || ""} readOnly />}
            {tab === "spec" && (
              <CodeEditor value={artifacts["workflow_spec.json"] || ""} language="json" readOnly />
            )}
            {tab === "policy" && (
              <CodeEditor value={artifacts["policy.json"] || ""} language="json" readOnly />
            )}
            {tab === "logs" && <LogsViewer logs={logs} />}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 items-center border-t border-slate-800 pt-4">
        <a
          href={downloadUrl(run.run_id)}
          className="rounded bg-emerald-700 hover:bg-emerald-600 px-4 py-2 text-sm font-medium"
        >
          Download deployable zip
        </a>
        {!preview ? (
          <button
            type="button"
            onClick={onPreviewStart}
            className="rounded bg-slate-700 hover:bg-slate-600 px-4 py-2 text-sm"
          >
            Start live preview
          </button>
        ) : (
          <>
            <a
              href={preview.app_url || preview.docs_url}
              target="_blank"
              rel="noreferrer"
              className="rounded bg-indigo-600 hover:bg-indigo-500 px-4 py-2 text-sm font-medium"
            >
              Open the app
            </a>
            <a
              href={preview.docs_url}
              target="_blank"
              rel="noreferrer"
              className="text-indigo-400 underline text-sm"
            >
              API docs
            </a>
            <button type="button" onClick={onPreviewStop} className="text-sm text-slate-400 underline">
              Stop preview
            </button>
          </>
        )}
        {previewError && <span className="text-red-400 text-sm">{previewError}</span>}
      </div>
    </div>
  );
}
