export default function LogsViewer({ logs }) {
  return (
    <pre className="h-full overflow-auto rounded-lg bg-black/40 p-3 text-xs text-slate-200 whitespace-pre-wrap">
      {logs || "No logs yet."}
    </pre>
  );
}
