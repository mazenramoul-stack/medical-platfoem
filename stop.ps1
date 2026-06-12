# Stop everything launched by start.ps1.
#
# Kills:
#   - Any python.exe running this project's manage.py runserver
#   - Any node.exe running this project's Vite dev server
# Leaves all OTHER python / node processes on the system alone.

$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

Write-Host ''
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host '  Stopping NEURACARD — Multimodal Medical AI Platform' -ForegroundColor Cyan
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''

$killed = 0

Write-Host 'Backend (Django manage.py runserver)...' -ForegroundColor Cyan
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*$root*manage.py*runserver*" } |
    ForEach-Object {
        Write-Host ('  killing pid {0}' -f $_.ProcessId)
        Stop-Process -Id $_.ProcessId -Force
        $script:killed += 1
    }

Write-Host 'Frontend (Vite dev server)...' -ForegroundColor Cyan
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object {
        $_.CommandLine -and
        $_.CommandLine -like "*$root*" -and
        ($_.CommandLine -like '*vite*' -or $_.CommandLine -like '*npm*dev*')
    } |
    ForEach-Object {
        Write-Host ('  killing pid {0}' -f $_.ProcessId)
        Stop-Process -Id $_.ProcessId -Force
        $script:killed += 1
    }

# ---------------------------------------------------------------------------
# Fallback: free the platform ports (3000 frontend, 8000 backend) even when a
# server was started outside start.ps1 (e.g. `npm run dev` in a plain shell).
# Only node.exe / python.exe owners are touched, to avoid hitting unrelated apps.
# ---------------------------------------------------------------------------
Write-Host 'Freeing ports 3000 / 8000 (node/python owners only)...' -ForegroundColor Cyan
foreach ($port in 3000, 8000) {
    Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object {
            $proc = Get-Process -Id $_ -ErrorAction SilentlyContinue
            if ($proc -and $proc.ProcessName -in @('node', 'python')) {
                Write-Host ('  freeing port {0} (pid {1}, {2})' -f $port, $proc.Id, $proc.ProcessName)
                Stop-Process -Id $proc.Id -Force
                $script:killed += 1
            }
        }
}

Write-Host ''
if ($killed -eq 0) {
    Write-Host 'No matching processes found.' -ForegroundColor Yellow
} else {
    Write-Host ('Stopped {0} process(es).' -f $killed) -ForegroundColor Green
}
Write-Host ''
