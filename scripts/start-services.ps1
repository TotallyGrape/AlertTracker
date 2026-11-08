param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$pythonExe = Join-Path $backendRoot '.venv\Scripts\python.exe'
$viteEntry = Join-Path $projectRoot 'node_modules\vite\bin\vite.js'
$logDirectory = Join-Path $projectRoot '.logs'

function Get-ServiceState($Url, $Expected) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        if ($response.Content -notmatch $Expected) {
            throw "A different service is responding at $Url. Stop it before starting Rally Point."
        }
        return $true
    } catch [System.Net.WebException] {
        if ($_.Exception.Response) { throw "An unexpected service is responding at $Url." }
        return $false
    }
}

try {
    $nodeExe = (Get-Command node.exe -ErrorAction Stop).Source
    if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Missing backend virtual environment. Run: python -m venv backend/.venv, then backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt' }
    if (-not (Test-Path -LiteralPath $viteEntry)) { throw 'Missing frontend dependencies. Run npm install in the project folder.' }
    & $pythonExe -c 'import fastapi, uvicorn, httpx, shapely, dotenv' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Missing Python dependencies. Run backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt' }
    $backendRunning = Get-ServiceState 'http://127.0.0.1:8000/openapi.json' 'Dallas Disaster Feed API'
    $frontendRunning = Get-ServiceState 'http://localhost:5173/' 'Rally Point'
    if (-not (Test-Path -LiteralPath (Join-Path $backendRoot '.env'))) { Write-Warning 'backend/.env is absent. Optional Spacetime synchronization and Nemotron may be disabled.' }
    if ($CheckOnly) {
        Write-Host "Checks passed. Backend already running: $backendRunning. Frontend already running: $frontendRunning."
        exit 0
    }
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    if (-not $backendRunning) {
        $process = Start-Process -FilePath $pythonExe -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port 8000' -WorkingDirectory $backendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory 'backend.out.log') -RedirectStandardError (Join-Path $logDirectory 'backend.err.log') -PassThru
        Write-Host "Started FastAPI (PID $($process.Id))."
    } else { Write-Host 'FastAPI is already running; leaving it unchanged.' }
    if (-not $frontendRunning) {
        $process = Start-Process -FilePath $nodeExe -ArgumentList ('"' + $viteEntry + '" --host localhost --port 5173 --strictPort') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory 'frontend.out.log') -RedirectStandardError (Join-Path $logDirectory 'frontend.err.log') -PassThru
        Write-Host "Started Vite (PID $($process.Id))."
    } else { Write-Host 'Vite is already running; leaving it unchanged.' }
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if ((Get-ServiceState 'http://127.0.0.1:8000/openapi.json' 'Dallas Disaster Feed API') -and (Get-ServiceState 'http://localhost:5173/' 'Rally Point')) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Services did not become ready. Inspect .logs/backend.err.log and .logs/frontend.err.log.' }
    Write-Host 'App: http://localhost:5173/'
    Write-Host 'API documentation: http://127.0.0.1:8000/docs'
    Write-Host "Background service logs: $logDirectory"
    Write-Host 'Feed loading, Spacetime synchronization and optional Nemotron work continue inside FastAPI.'
    Write-Host 'Existing services are reused; run again after stopping them to load backend code changes.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
