// In dev, always use Vite proxy (/api → 8003). Direct VITE_API_BASE causes CORS / wrong port.
const API_BASE =
  import.meta.env.DEV && import.meta.env.VITE_FORCE_API_BASE !== "1"
    ? ""
    : import.meta.env.VITE_API_BASE || "";

export async function fetchConfig() {
  const res = await fetch(`${API_BASE}/api/v1/config`);
  return res.json();
}

export async function fetchBenchmarks() {
  const res = await fetch(`${API_BASE}/api/v1/benchmarks`);
  return res.json();
}

export async function runWorkflow(body) {
  const res = await fetch(`${API_BASE}/api/v1/workflows/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  return res.json();
}

export async function fetchRun(runId) {
  const res = await fetch(`${API_BASE}/api/v1/runs/${runId}`);
  if (!res.ok) throw new Error("Run not found");
  return res.json();
}

export function downloadUrl(runId) {
  return `${API_BASE}/api/v1/runs/${runId}/download`;
}

export async function startPreview(runId) {
  const res = await fetch(`${API_BASE}/api/v1/runs/${runId}/preview/start`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function stopPreview(runId) {
  const res = await fetch(`${API_BASE}/api/v1/runs/${runId}/preview/stop`, { method: "POST" });
  return res.json();
}

export async function startExperiment(body) {
  const res = await fetch(`${API_BASE}/api/v1/experiments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchGrids() {
  const res = await fetch(`${API_BASE}/api/v1/grid`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchGrid(name) {
  const res = await fetch(`${API_BASE}/api/v1/grid/${encodeURIComponent(name)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchCompare(name, task, repeat) {
  const q = new URLSearchParams({ task, repeat: String(repeat) });
  const res = await fetch(`${API_BASE}/api/v1/grid/${encodeURIComponent(name)}/compare?${q}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function chartUrl(name, file) {
  return `${API_BASE}/api/v1/grid/${encodeURIComponent(name)}/charts/${encodeURIComponent(file)}`;
}
