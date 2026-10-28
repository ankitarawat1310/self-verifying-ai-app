# Start SVAGA 3.0 API (8003) + console UI (5303). SVAGA 2.0 uses 5173 + 8000.
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:PYTHONPATH = "."
$env:SVAGA_SCRIPTED_LLM = "1"

$apiPort = if ($env:SVAGA_API_PORT) { $env:SVAGA_API_PORT } else { "8003" }

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$Root'; `$env:PYTHONPATH='.'; `$env:SVAGA_SCRIPTED_LLM='1'; python -m uvicorn svaga_platform.app.main:app --reload --host 127.0.0.1 --port $apiPort"
)

Start-Sleep -Seconds 2
Set-Location "$Root\model1_rag_generator\frontend"
$env:VITE_PROXY_TARGET = "http://127.0.0.1:$apiPort"
$env:VITE_DEV_PORT = "5303"
npm run dev
