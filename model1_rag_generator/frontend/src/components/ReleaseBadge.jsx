export default function ReleaseBadge({ decision, reasons = [] }) {
  if (!decision) return null;
  const accept = decision === "ACCEPT";
  return (
    <div className="flex flex-col gap-1">
      <span
        className={`inline-flex w-fit rounded-full px-3 py-1 text-xs font-bold ${
          accept ? "bg-emerald-600" : "bg-red-600"
        }`}
      >
        {decision}
      </span>
      {!accept && reasons?.length > 0 && (
        <ul className="text-xs text-red-300 list-disc ml-4">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
