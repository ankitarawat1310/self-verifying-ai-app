export default function VerifierTable({ verifiers = [] }) {
  if (!verifiers.length) return <p className="text-sm text-slate-400">No verifiers yet.</p>;
  return (
    <table className="w-full text-sm border border-slate-800 rounded overflow-hidden">
      <thead className="bg-slate-900">
        <tr>
          <th className="text-left p-2">Verifier</th>
          <th className="text-left p-2">Status</th>
          <th className="text-right p-2">Time (s)</th>
        </tr>
      </thead>
      <tbody>
        {verifiers.map((v) => (
          <tr key={v.name} className="border-t border-slate-800">
            <td className="p-2 font-mono text-xs">{v.name}</td>
            <td className="p-2">{v.passed ? "PASS" : "FAIL"}</td>
            <td className="p-2 text-right">{v.wall_seconds ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
