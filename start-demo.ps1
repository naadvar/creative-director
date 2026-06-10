# start-demo.ps1 — bring the Creative Director demo back up after a logout/sleep.
# Restarts the local backend + Cloudflare tunnel, then auto-re-points the Vercel
# /api proxy at the new tunnel URL (commit + push) so the public URL keeps working.
#
# Usage: double-click start-demo.bat  (or: right-click this file -> Run with PowerShell)
# One-time setup: put a GitHub token (repo scope) in a file named .demo-gh-token
#   in this folder. It's gitignored and never leaves your machine.

$ErrorActionPreference = "Continue"
$repo      = $PSScriptRoot
$vercelUrl = "https://creative-director-psi.vercel.app"
$py        = Join-Path $repo ".venv\Scripts\python.exe"
$cf        = Join-Path $repo "cloudflared.exe"
$vj        = Join-Path $repo "frontend\vercel.json"
$tokenFile = Join-Path $repo ".demo-gh-token"

Write-Host "== Creative Director demo: restarting ==" -ForegroundColor Cyan

# 1) Stop any old backend + tunnel
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'uvicorn api.main' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 2) Start the backend (browse-only demo settings)
$env:API_FRONTEND_BASE_URL = $vercelUrl
$env:ENABLE_INGEST = "false"
Start-Process -FilePath $py `
  -ArgumentList @("-m","uvicorn","api.main:app","--port","8000","--host","127.0.0.1") `
  -WorkingDirectory $repo -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $repo "backend.out.log") `
  -RedirectStandardError  (Join-Path $repo "backend.err.log")
Write-Host "backend starting..."
for ($i=0; $i -lt 30; $i++) {
  try { Invoke-WebRequest "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 3 | Out-Null; Write-Host "backend up." -ForegroundColor Green; break }
  catch { Start-Sleep -Seconds 2 }
}

# 3) Start the tunnel and capture its new public URL
Remove-Item (Join-Path $repo "tunnel.log") -ErrorAction SilentlyContinue
Start-Process -FilePath $cf `
  -ArgumentList @("tunnel","--url","http://localhost:8000","--no-autoupdate") `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $repo "tunnel.out.log") `
  -RedirectStandardError  (Join-Path $repo "tunnel.log")
Write-Host "tunnel starting..."
$tunnel = $null
for ($i=0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 2
  $hit = Select-String -Path (Join-Path $repo "tunnel.log"),(Join-Path $repo "tunnel.out.log") `
           -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($hit) { $tunnel = $hit.Matches[0].Value; break }
}
if (-not $tunnel) { Write-Host "ERROR: no tunnel URL (see tunnel.log)" -ForegroundColor Red; exit 1 }
Write-Host "tunnel: $tunnel" -ForegroundColor Green

# 4) Re-point the Vercel /api proxy at the new tunnel
$content = (Get-Content $vj -Raw) -replace 'https://[a-z0-9-]+\.trycloudflare\.com', $tunnel
[System.IO.File]::WriteAllText($vj, $content, (New-Object System.Text.UTF8Encoding $false))

# 5) Commit + push so Vercel rebuilds the proxy
if (-not (Test-Path $tokenFile)) { Write-Host "ERROR: missing .demo-gh-token (put a GitHub token in it)" -ForegroundColor Red; exit 1 }
$token = (Get-Content $tokenFile -Raw).Trim()
git -C $repo add frontend/vercel.json
git -C $repo commit -m "demo: repoint Vercel proxy at $tunnel" | Out-Null
git -C $repo -c credential.helper= push "https://$token@github.com/naadvar/creative-director.git" main 2>&1 |
  ForEach-Object { $_ -replace 'ghp_[A-Za-z0-9_]+','ghp_***' }

# 6) Pre-warm the niche benchmarks so the first visitor isn't slow
Write-Host "pre-warming niches..."
foreach ($v in @("ig_9guIKXBDn_","ig_B-pj_Z2BE2L","ig_-FFoqmyLLD")) {
  try { Invoke-WebRequest "http://127.0.0.1:8000/videos/$v/summary" -UseBasicParsing -TimeoutSec 60 | Out-Null } catch {}
}

Write-Host ""
Write-Host "DONE - live in ~1-2 min at:  $vercelUrl" -ForegroundColor Cyan
Write-Host "(Vercel is rebuilding the proxy. Keep this machine awake.)"
