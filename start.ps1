# Multimodal Medical AI Platform — one-shot launcher.
#
# Opens the Django backend on http://localhost:8000 and the Vite frontend
# on http://localhost:3000 in two new PowerShell windows, then opens the
# browser. Closing THIS window does not stop the servers — close the two
# spawned windows (or run stop.ps1) when you're done.
#
# Usage:
#   PowerShell:   .\start.ps1
#   Double-click: start.bat (wrapper that bypasses execution policy)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Force UTF-8 in this console so any non-ASCII output renders correctly
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Write-Header($text) {
    Write-Host ''
    Write-Host '================================================================' -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host '================================================================' -ForegroundColor Cyan
    Write-Host ''
}

function Test-Port($port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect('127.0.0.1', $port)
        $c.Close()
        return $true
    } catch { return $false }
}

Write-Header 'NEURACARD — Multimodal Medical AI — Starting up'

# ---------------------------------------------------------------------------
# 1. Sanity checks
# ---------------------------------------------------------------------------

$pyExe       = Join-Path $root 'backend\venv\Scripts\python.exe'
$frontPkg    = Join-Path $root 'frontend\package.json'
$frontNodeMd = Join-Path $root 'frontend\node_modules'

if (-not (Test-Path $pyExe)) {
    Write-Host '[ERROR] Backend virtualenv not found at:' -ForegroundColor Red
    Write-Host "        $pyExe" -ForegroundColor Red
    Write-Host ''
    Write-Host 'Fix: from the backend/ directory, create the venv and install requirements:' -ForegroundColor Yellow
    Write-Host '     python -m venv venv'                                                     -ForegroundColor Yellow
    Write-Host '     .\venv\Scripts\Activate.ps1'                                             -ForegroundColor Yellow
    Write-Host '     pip install -r requirements.txt'                                         -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $frontPkg)) {
    Write-Host "[ERROR] frontend\package.json not found." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $frontNodeMd)) {
    Write-Host '[ERROR] frontend\node_modules is missing.' -ForegroundColor Red
    Write-Host 'Fix:   cd frontend ; npm install' -ForegroundColor Yellow
    exit 1
}

# ---------------------------------------------------------------------------
# 2. MongoDB reachable?
# ---------------------------------------------------------------------------

Write-Host '[1/4] MongoDB on localhost:27017... ' -NoNewline
if (Test-Port 27017) {
    Write-Host 'OK' -ForegroundColor Green
} else {
    Write-Host 'NOT REACHABLE' -ForegroundColor Red
    Write-Host ''
    Write-Host 'MongoDB is not listening. Start it first:' -ForegroundColor Yellow
    Write-Host '   net start MongoDB        (admin)'        -ForegroundColor Yellow
    Write-Host '   - or -'                                  -ForegroundColor Yellow
    Write-Host '   mongod --dbpath <path>'                  -ForegroundColor Yellow
    Write-Host ''
    $reply = Read-Host 'Continue anyway? [y/N]'
    if ($reply -notmatch '^[yY]') { exit 1 }
}

# ---------------------------------------------------------------------------
# 3. Port conflict warnings
# ---------------------------------------------------------------------------

Write-Host '[2/4] Checking ports... ' -NoNewline
$portIssues = @()
if (Test-Port 8000) { $portIssues += 'port 8000 (backend)' }
if (Test-Port 3000) { $portIssues += 'port 3000 (frontend)' }
if ($portIssues.Count -eq 0) {
    Write-Host 'OK' -ForegroundColor Green
} else {
    Write-Host 'CONFLICT' -ForegroundColor Yellow
    foreach ($p in $portIssues) {
        Write-Host "      Something is already listening on $p." -ForegroundColor Yellow
    }
    Write-Host '      The new server(s) will refuse to bind. Free the port(s) first:' -ForegroundColor Yellow
    Write-Host '         Get-NetTCPConnection -LocalPort 3000 | Select OwningProcess' -ForegroundColor Yellow
    Write-Host '         Stop-Process -Id <pid> -Force'                                -ForegroundColor Yellow
    Write-Host ''
    $reply = Read-Host 'Continue anyway? [y/N]'
    if ($reply -notmatch '^[yY]') { exit 1 }
}

# ---------------------------------------------------------------------------
# 4. Launch backend in a new window
# ---------------------------------------------------------------------------

Write-Host '[3/4] Starting Django backend on http://localhost:8000 ...' -ForegroundColor Cyan
$backendCmd = @"
`$Host.UI.RawUI.WindowTitle = 'NEURACARD - Backend (Django)'
Set-Location '$root\backend'
& '$pyExe' manage.py runserver
Write-Host ''
Write-Host '[Backend stopped] Close this window or press Enter.' -ForegroundColor Yellow
Read-Host
"@
Start-Process powershell -ArgumentList '-NoExit','-NoProfile','-Command',$backendCmd -WindowStyle Normal | Out-Null

# ---------------------------------------------------------------------------
# 5. Launch frontend in a new window
# ---------------------------------------------------------------------------

Start-Sleep -Seconds 2  # let the backend bind first

Write-Host '[4/4] Starting Vite frontend on http://localhost:3000 ...' -ForegroundColor Cyan
$frontendCmd = @"
`$Host.UI.RawUI.WindowTitle = 'NEURACARD - Frontend (Vite)'
Set-Location '$root\frontend'
npm run dev
Write-Host ''
Write-Host '[Frontend stopped] Close this window or press Enter.' -ForegroundColor Yellow
Read-Host
"@
Start-Process powershell -ArgumentList '-NoExit','-NoProfile','-Command',$frontendCmd -WindowStyle Normal | Out-Null

# ---------------------------------------------------------------------------
# 6. Wait briefly, then open the browser
# ---------------------------------------------------------------------------

Start-Sleep -Seconds 4
Write-Header 'All systems go'

Write-Host '  Backend:   http://localhost:8000'
Write-Host '  Frontend:  http://localhost:3000'
Write-Host '  Admin:     http://localhost:8000/admin/'
Write-Host ''
Write-Host '  Default seed login (run backend\tests\seed_database.py to create it):'
Write-Host '    Email:    doctor@test.com'
Write-Host '    Password: TestPass123!'
Write-Host ''
Write-Host '  To stop the servers:'
Write-Host '    - Close the two PowerShell windows that just opened, or'
Write-Host '    - Run:  .\stop.ps1'
Write-Host ''

try { Start-Process 'http://localhost:3000' } catch {}
