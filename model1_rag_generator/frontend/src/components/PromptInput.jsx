export default function PromptInput({ value, onChange, onSubmit, loading, label = "Generate" }) {
  return (
    <div className="flex flex-col gap-2 h-full">
      <label className="text-sm font-medium text-slate-300">Workflow prompt</label>
      <textarea
        className="flex-1 min-h-[200px] rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Describe the small app to generate..."
      />
      <button
        type="button"
        disabled={loading}
        onClick={onSubmit}
        className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold disabled:opacity-50"
      >
        {loading ? "Generating… (about a minute with a local model)" : label}
      </button>
    </div>
  );
}
