import { Link } from "react-router-dom";

export default function Home() {
  return (
    <div className="max-w-2xl mx-auto py-16 px-4 space-y-6">
      <p className="text-xs uppercase tracking-wide text-indigo-400">
        SVAGA 3.0 only — console port 5303 · API 8003
      </p>
      <h1 className="text-3xl font-bold">SVAGA 3.0 Console</h1>
      <p className="text-slate-300">
        Self-Verifying Agent-Generated Applications — natural language to a small deployable app with
        specifications, tests, least-privilege policy, multi-verifier checks, and release gate
        (ACCEPT / REJECT).
      </p>
      <div className="flex gap-3">
        <Link
          to="/create"
          className="rounded-lg bg-indigo-600 hover:bg-indigo-500 px-4 py-2 font-medium"
        >
          New workflow run
        </Link>
        <Link to="/experiments" className="rounded-lg bg-slate-700 hover:bg-slate-600 px-4 py-2">
          Compare pipelines (M1–M4)
        </Link>
      </div>
    </div>
  );
}
