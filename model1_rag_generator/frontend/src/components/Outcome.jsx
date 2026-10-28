// One run's outcome: the model's own decision against the hidden judge. Always a word plus a color, never color alone.
export const OUTCOMES = {
  shipped_ok: { label: "Shipped, correct", cls: "bg-emerald-700 text-white" },
  shipped_broken: { label: "Shipped, broken", cls: "bg-red-700 text-white" },
  rejected_ok: { label: "Rejected, but correct", cls: "bg-amber-400 text-slate-950" },
  rejected_broken: { label: "Rejected, broken", cls: "bg-slate-600 text-white" },
  error: { label: "Error", cls: "bg-slate-800 text-slate-200 border border-slate-600" },
};

export function outcomeOf(run) {
  if (!run) return null;
  if (run.decision === "ERROR") return "error";
  const shipped = run.decision === "ACCEPT";
  if (shipped) return run.hidden_pass ? "shipped_ok" : "shipped_broken";
  return run.hidden_pass ? "rejected_ok" : "rejected_broken";
}

export default function Outcome({ run, compact = false }) {
  const key = outcomeOf(run);
  if (!key) return <span className="text-slate-600 text-xs">-</span>;
  const o = OUTCOMES[key];
  return (
    <span className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold ${o.cls}`}>
      {compact ? `${run.hidden_passed}/${run.hidden_total}` : `${o.label} · ${run.hidden_passed}/${run.hidden_total}`}
    </span>
  );
}
