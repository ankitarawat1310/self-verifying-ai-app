const STEPS = ["Workflow", "Retrieve", "Generate", "Verify", "Release", "Ship"];

export default function RunStepper({ activeIndex = 0 }) {
  return (
    <ol className="flex flex-wrap gap-2 text-xs mb-4">
      {STEPS.map((label, i) => (
        <li
          key={label}
          className={`px-2 py-1 rounded ${
            i <= activeIndex ? "bg-indigo-700 text-white" : "bg-slate-800 text-slate-400"
          }`}
        >
          {i + 1}. {label}
        </li>
      ))}
    </ol>
  );
}
